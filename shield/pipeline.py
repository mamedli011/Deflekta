"""Shield pipeline (Role 4 owns this file). Glue for layers 1-3.

Public interface (see contracts/interfaces.py):
    check_action(tool, args) -> ActionDecision
    check_input(url, page_text, raw_html=None, scan=None) -> InputDecision
        scan (optional, R4-T2b): a layer-1 scan from the same page load (browse_web rendered mode,
        ToolResult.meta["scan"]). Reused if usable for this exact URL; otherwise we render as before.
    wrap_tools(execute_fn) -> guarded execute_fn        TODO (bonus, after CP3)

Layer ablation: env SHIELD_LAYERS, e.g. "1,2,3" (default), "3" (action guard only), "1,3".
The benchmark runs Shield ON with each setting to show what each layer contributes.

STATUS: implemented and tested. Real Chromium layer-1 scan (tests/test_pipeline_real.py), same-load
scan reuse (tests/test_pipeline_scan_reuse.py), Gemini judge with local grounding and hidden_complete
checks (tests/test_judge.py; tests/conftest.py blocks live judge calls in the suite).
"""
from __future__ import annotations

import os
import re
from typing import Any

from contracts.interfaces import ActionDecision, InputDecision
from shield import gap as gapmod
from shield.action_guard import ActionGuard

_GUARD = ActionGuard()
LOW_SEVERITY_MAX_CHARS = 60   # short hidden strings (skip links, menu labels) are only FLAGGED
VISIBLE_FLAG_CONFIDENCE = 0.8  # a grounded visible instruction at or above this is flagged and removed
MIN_VISIBLE_QUOTE = 15         # shorter judge quotes never remove visible text (too generic to trust)
VISIBLE_PLACEHOLDER = "[instruction to the AI removed by shield]"


# Structure inside one html2text line that a removal must not eat: table cell separators ("a | b"), and a
# leading list marker / heading / blockquote / emphasised label with a colon ("- **Step 3:** ...").
_CELL_BEFORE = re.compile(r"\|[ \t]+")
_CELL_AFTER = re.compile(r"[ \t]+\|")
_LEAD = re.compile(r"(?:[ \t]*(?:[-*+]|\d{1,3}[.)])[ \t]+|[ \t]*>[ \t]*|[ \t]*#{1,6}[ \t]+)*"
                   r"(?:[ \t]*(?:\*\*[^*\n]{1,60}?:\*\*|\*\*[^*\n]{1,60}?\*\*:|__[^_\n]{1,60}?:__)[ \t]+)?")


def remove_quoted_instruction(text: str, quote: str) -> tuple[str, list[str]]:
    """Remove the sentence around each exact occurrence of `quote` in `text`. A removed piece runs from the
    sentence boundary before the quote to the one after it (same splitter as shield/gap.py), never past a
    newline or a table-cell separator, and keeps a leading list marker / heading / labelled prefix, so table
    labels and list structure stay. Overlapping pieces are merged. Returns (new_text, removed_pieces); a
    quote that is too short or not found changes nothing."""
    if len(quote.strip()) < MIN_VISIBLE_QUOTE or quote not in text:
        return text, []
    ranges: list[list[int]] = []
    i = text.find(quote)
    while i != -1:
        j = i + len(quote)
        line_start = text.rfind("\n", 0, i) + 1
        line_end = text.find("\n", j)
        line_end = len(text) if line_end == -1 else line_end
        start = line_start
        for m in gapmod._SPLIT.finditer(text, line_start, i):
            start = m.end()
        for m in _CELL_BEFORE.finditer(text, start, i):       # stay inside the quote's table cell
            start = m.end()
        lead = _LEAD.match(text, start, i)                     # keep list markers / labelled prefixes
        if lead:
            start = lead.end()
        after = gapmod._SPLIT.search(text, j, line_end)
        end = after.start() if after else line_end
        cell = _CELL_AFTER.search(text, j, end)
        if cell:
            end = cell.start()
        if ranges and start <= ranges[-1][1]:
            ranges[-1][1] = max(ranges[-1][1], end)          # overlapping piece: remove once
        else:
            ranges.append([start, end])
        i = text.find(quote, j)
    out, removed, pos = [], [], 0
    for start, end in ranges:
        out += [text[pos:start], VISIBLE_PLACEHOLDER]
        removed.append(text[start:end])
        pos = end
    out.append(text[pos:])
    return "".join(out), removed


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


def _allowed_reason(layers: set[int], render_failed: bool, render_note: str, judge_known: bool) -> str:
    """Explain an ALLOWED result by what actually ran. Text only: it never changes the decision."""
    if 1 not in layers and 2 not in layers:
        return "Not inspected: input layers 1 and 2 are off (SHIELD_LAYERS)"
    if 1 not in layers:
        parts = ["Layer 1 off (no hidden-text check)"]
    elif render_failed:
        parts = ["Hidden-text check not done" + render_note]
    else:
        parts = ["No hidden text found"]
    if 2 not in layers:
        parts.append("judge (layer 2) off")
    elif judge_known:
        parts.append("the judge did not flag the visible text")
    else:
        parts.append("no usable judge answer (unavailable or ungrounded)")
    return "; ".join(parts)


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
    # For hidden text the judge must also have seen all of it; a partial view counts as "no judge".
    hidden_known = bool(judge_known and verdict_j.get("hidden_complete") is True)
    hidden_instruction = bool(hidden_known and verdict_j.get("is_instruction_to_ai"))
    try:
        conf = float(verdict_j.get("confidence", 0)) if verdict_j else 0.0
    except (TypeError, ValueError):
        conf = 0.0

    def remove_visible(text: str) -> tuple[str, dict | None, str]:
        """A grounded visible instruction (>= 0.8) still in `text` after layer 1 is removed. The removed
        pieces are recorded locally on a copy of the judge evidence (never taken from the model)."""
        if not (judged_instruction and conf >= VISIBLE_FLAG_CONFIDENCE):
            return text, verdict_j, ""
        new, removed = remove_quoted_instruction(text, str(verdict_j.get("quoted_span") or ""))
        if not removed:
            return text, verdict_j, ""
        return new, {**verdict_j, "removed_visible": removed}, "; the instruction to the AI was removed"

    if spans:
        clean, evidence, note = remove_visible(gapmod.strip(page_text, spans))
        note = note.replace("the instruction", "a visible instruction")
        serious = [s for s in spans if _is_serious(s, noscript)]
        if hidden_instruction and conf >= 0.6 or (serious and not hidden_known):
            return InputDecision(verdict="STRIPPED", clean_text=clean, severity="high", layer=1,
                                 rule_triggered="hidden_from_human_fed_to_ai",
                                 reason="The page fed the AI text that a person can't see; it was removed" + note,
                                 segments=[{"text": s} for s in spans] + segments[:10], judge=evidence)
        return InputDecision(verdict="FLAGGED", clean_text=clean, severity="low", layer=1,
                             rule_triggered="hidden_text_not_instruction",
                             reason="Hidden text found (likely menus or screen-reader text); removed as a precaution"
                                    + note,
                             segments=[{"text": s} for s in spans] + segments[:10], judge=evidence)
    if judged_instruction and conf >= VISIBLE_FLAG_CONFIDENCE:
        clean, evidence, note = remove_visible(page_text)
        return InputDecision(verdict="FLAGGED", clean_text=clean, severity="medium", layer=2,
                             rule_triggered="visible_instruction_to_ai",
                             reason="Visible page text appears to give instructions to the AI" + note + render_note,
                             judge=evidence, render_failed=render_failed)
    return InputDecision(verdict="ALLOWED", clean_text=page_text, judge=verdict_j, render_failed=render_failed,
                         reason=_allowed_reason(layers, render_failed, render_note, judge_known))
