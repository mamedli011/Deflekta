"""Shared interfaces. The ONLY place cross-role types and signatures are defined.

Agreed at kickoff. Do not rename or remove anything here without telling the whole team.
Adding optional fields with defaults is fine.

Call graph:
    frontend  -> agent.loop.run_agent(task, shield_on, session_id)
    agent     -> sandbox.tools.execute(tool, args)                 every tool call
    agent     -> shield.pipeline.check_action(tool, args)          before execute, if shield_on
    agent     -> shield.pipeline.check_input(url, page_text, ...)  after browse_web, if shield_on
    everyone  -> agent.events.log_event(...)                       one JSON line per decision
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Verdict = Literal["ALLOWED", "FLAGGED", "STRIPPED", "NEEDS_CONFIRM", "BLOCKED"]
Severity = Literal["low", "medium", "high", "critical"]
Stage = Literal["input", "action", "agent", "final"]
ToolName = Literal["browse_web", "read_email", "read_file", "send_email", "http_request", "delete_file"]


@dataclass
class ActionDecision:
    """Returned by shield.pipeline.check_action. Mirrors shield.action_guard.Decision."""
    verdict: Verdict = "ALLOWED"
    rule_triggered: str | None = None
    severity: Severity | None = None
    reason: str = "No rule matched"
    evidence: dict[str, Any] = field(default_factory=dict)
    layer: int | None = 3


@dataclass
class InputDecision:
    """Returned by shield.pipeline.check_input for one page."""
    verdict: Verdict                      # ALLOWED, FLAGGED, or STRIPPED
    clean_text: str                       # what the agent should receive (hidden instructions removed)
    severity: Severity | None = None
    layer: int | None = None              # 1 or 2, whichever decided
    rule_triggered: str | None = None     # e.g. "hidden_computed_style", "judge_instruction"
    reason: str = ""
    segments: list[dict[str, Any]] = field(default_factory=list)   # layer-1 HiddenSegment dicts
    judge: dict[str, Any] | None = None   # layer-2 raw verdict
    render_failed: bool = False


@dataclass
class ToolResult:
    """Returned by sandbox.tools.execute."""
    ok: bool
    output: Any                           # str for browse_web/read_file, list for read_email, str note for log-only tools
    side_effect: Literal["none", "logged_only"] = "none"
    error: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)   # e.g. {"url": ..., "raw_html": ...} for browse_web


@dataclass
class RunResult:
    """Returned by agent.loop.run_agent."""
    session_id: str
    shield_on: bool
    final_answer: str
    events_path: str                      # runs/<session_id>.jsonl
    steps: int
    hijacked: bool                        # exfiltration (canary in a log-only tool call) OR answer manipulation
    error: str | None = None
    hijack_kind: str | None = None        # "exfiltration" | "answer_manipulation" | None
