"""Shield pipeline (Role 4 owns this file). Glue for layers 1-3.

Public interface (see contracts/interfaces.py):
    check_action(tool, args) -> ActionDecision
    check_input(url, page_text, raw_html=None, scan=None) -> InputDecision
        scan (optional, R4-T2b): a layer-1 scan from the same page load (browse_web rendered mode,
        ToolResult.meta["scan"]). Reused if usable for this exact URL; otherwise we render as before.
    wrap_tools(execute_fn) -> guarded execute_fn        TODO (bonus, after CP3)

Layer ablation: env SHIELD_LAYERS, e.g. "1,2,3" (default), "3" (action guard only), "1,3".
The benchmark runs Shield ON with each setting to show what each layer contributes.

STATUS: decision logic tested with a faked layer-1 scan (tests/test_pipeline_input.py).
The real scan (Playwright) and the judge (layer 2) are R4-T1 / R4-T4.
"""
from __future__ import annotations

import os
from typing import Any

from contracts.interfaces import ActionDecision, InputDecision
from shield import gap as gapmod
from shield.action_guard import ActionGuard

_GUARD = ActionGuard()
LOW_SEVERITY_MAX_CHARS = 60   # short hidden strings (skip links, menu labels) are only FLAGGED


def enabled_layers() -> set[int]:
    raw = os.environ.get("SHIELD_LAYERS", "1,2,3")
    return {int(x) for x in raw.split(",") if x.strip()}


def check_action(tool: str, args: dict[str, Any] | None) -> ActionDecision:
    if 3 not in enabled_layers():
        return ActionDecision(verdict="ALLOWED", reason="layer 3 disabled (ablation)", layer=None)
    d = _GUARD.evaluate(tool, args or {})
    return ActionDecision(verdict=d.verdict, rule_triggered=d.rule_triggered, severity=d.severity,
                          reason=d.reason, evidence=d.evidence,
                          layer=3 if d.rule_triggered else None)


def _scan(url: str) -> dict:
    """Layer-1 render. Isolated so tests can replace it. Never raises."""
    try:
        from shield.visibility_gap import scan_url
        return scan_url(url)
    except Exception as exc:  # playwright missing/broken, browser crash: report, don't crash the demo
        return {"render_failed": True, "error": repr(exc), "segments": [], "human_html": None}


def _judge(visible_text: str, spans: list[str]) -> dict | None:
    """Layer 2. Returns None if the judge is unavailable (stub, quota, bad JSON). Never raises."""
    try:
        from shield.judge import judge
        return judge(visible_text, [{"text": s} for s in spans])
    except Exception:
        return None


def _norm_set(texts: list[str]) -> str:
    return " || ".join(gapmod._norm(t) for t in texts)


def _is_serious(span: str, noscript: str) -> bool:
    """Long gap sentences are serious, unless they come from <noscript> ("please enable JavaScript").
    Those are still stripped, but only FLAGGED unless the judge says they instruct the AI."""
    return len(span) > LOW_SEVERITY_MAX_CHARS and not (noscript and gapmod._norm(span) in noscript)


def _usable_scan(scan: Any, url: str) -> bool:
    """True if a supplied scan is a successful layer-1 scan of exactly this URL, with the shape
    scan_url() returns. Anything else is ignored and we render the page ourselves."""
    if not isinstance(scan, dict) or scan.get("url") != url or scan.get("render_failed") is not False:
        return False
    human_html = scan.get("human_html")
    if not isinstance(human_html, str) or not human_html.strip():
        return False
    noscript = scan.get("noscript_text", [])
    return (isinstance(scan.get("segments", []), list) and isinstance(noscript, list)
            and all(isinstance(t, str) for t in noscript))


def check_input(url: str, page_text: str, raw_html: str | None = None,
                scan: dict | None = None) -> InputDecision:
    layers = enabled_layers()
    spans: list[str] = []
    segments: list[dict] = []
    noscript = ""
    render_failed, render_note = False, ""
    if 1 in layers:
        # Reuse the same-load scan from browse_web when it's valid, so Chromium isn't run twice (R4-T2b).
        layer1 = scan if _usable_scan(scan, url) else _scan(url)
        if layer1.get("render_failed") or not layer1.get("human_html"):
            # Fail safe, not open: layer 1 is skipped but the judge (layer 2) still reads the page.
            render_failed = True
            render_note = f" (layer 1 could not render the page: {layer1.get('error', 'no output')})"
        else:
            segments = layer1.get("segments", [])
            noscript = _norm_set(layer1.get("noscript_text", []))
            spans = gapmod.gap(page_text, gapmod.to_text(layer1["human_html"]))

    verdict_j = _judge(page_text, spans) if 2 in layers else None
    # An ungrounded verdict stays in the evidence but counts as "no judge" for decisions.
    judge_known = bool(verdict_j and verdict_j.get("grounded"))
    judged_instruction = bool(judge_known and verdict_j.get("is_instruction_to_ai"))
    try:
        conf = float(verdict_j.get("confidence", 0)) if verdict_j else 0.0
    except (TypeError, ValueError):
        conf = 0.0

    if spans:
        clean = gapmod.strip(page_text, spans)
        serious = [s for s in spans if _is_serious(s, noscript)]
        if judged_instruction and conf >= 0.6 or (serious and not judge_known):
            return InputDecision(verdict="STRIPPED", clean_text=clean, severity="high", layer=1,
                                 rule_triggered="hidden_from_human_fed_to_ai",
                                 reason="The page fed the AI text that a person can't see; it was removed",
                                 segments=[{"text": s} for s in spans] + segments[:10], judge=verdict_j)
        return InputDecision(verdict="FLAGGED", clean_text=clean, severity="low", layer=1,
                             rule_triggered="hidden_text_not_instruction",
                             reason="Hidden text found (likely menus or screen-reader text); removed as a precaution",
                             segments=[{"text": s} for s in spans] + segments[:10], judge=verdict_j)
    if judged_instruction and conf >= 0.8:
        return InputDecision(verdict="FLAGGED", clean_text=page_text, severity="medium", layer=2,
                             rule_triggered="visible_instruction_to_ai",
                             reason="Visible page text appears to give instructions to the AI" + render_note,
                             judge=verdict_j, render_failed=render_failed)
    return InputDecision(verdict="ALLOWED", clean_text=page_text, judge=verdict_j, render_failed=render_failed,
                         reason=("No hidden or instruction-like content" + render_note).strip())
