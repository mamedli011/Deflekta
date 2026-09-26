# 11. Sources and Verification Log

## Verified by running code (planning environment, Sept 26, 2026)
Script: `scripts/verify_baseline_gap.py`. Payload was reworded to avoid classic trigger
phrases. Results:

**sentinel-security 0.9.0, `sanitise_content(html, format="html")`:**

| Technique | Result |
|-----------|--------|
| inline display:none | MEDIUM (hidden_html) |
| inline font-size:0 | MEDIUM (hidden_html) |
| class hidden in inline `<style>` | MEDIUM (css_class_hiding) |
| class off-screen in inline `<style>` | MEDIUM (css_class_hiding) |
| inline white-on-white | **CLEAN** |
| class in external stylesheet | **CLEAN** |
| inherited near-white color | **CLEAN** |
| img alt text (which html2text and markdownify DO pass to the model) | **CLEAN** |
| aria-label | CLEAN (but converters drop it too, so low risk for raw-HTML agents) |
| HTML comment | MEDIUM (hidden_html) |
| visible reworded instruction | CLEAN (expected: that's layer 2's job) |

**Do converters pass hidden text to the model?** (html2text 2025.4.15, markdownify 1.2.2, bs4 get_text)

| Technique | html2text | markdownify | bs4 get_text |
|-----------|-----------|-------------|--------------|
| display:none (inline or class) | passes | passes | passes |
| white-on-white / inherited color | passes | passes | passes |
| off-screen | passes | passes | passes |
| img alt | passes | passes | dropped |
| aria-label | dropped | dropped | dropped |
| HTML comment | dropped | dropped | dropped |

JavaScript-injected text (our `recipe_js_injected.html`): html2text on the raw HTML does NOT
include it, because it only exists after scripts run. So that technique only threatens agents
that render pages (AI browsers). The sandbox spec (doc 06) includes both modes; say which one a demo uses.

Conclusion: CSS-hidden text reaches the model through common converters. aria-label and
comments only matter if an agent reads raw HTML or the accessibility tree.
Re-run the script on your machines before quoting it; versions can change behavior.

## Verified by tests in this repo (run `pytest -q`)
- `tests/test_gap.py`: the agent-view vs human-view diff finds a hidden div and alt text, strips
  only the hidden sentence, and does not flag JS-injected text for a raw-mode agent.
- `tests/test_agent_loop_offline.py`: the real agent loop with a scripted, gullible fake model.
  Exfiltration: OFF hijacked, ON blocked, recipe still delivered. Answer manipulation: OFF hijacked,
  layer-3-only still hijacked, all layers protected.
These use a fake model and a faked render. The real-model numbers come from the benchmark.

## Verified from official or primary sources

| Claim | Source |
|-------|--------|
| Gemini API rate limits are per project, not per key; RPD resets midnight Pacific; limits viewed in AI Studio | ai.google.dev/gemini-api/docs/rate-limits (updated 2026-09-02) |
| Prompt injection is LLM01 in the OWASP Top 10 for LLM Applications 2025; the list also includes excessive agency | OWASP GenAI project (owasp.org) and multiple 2026 summaries |
| AgentDojo: ETH Zurich + Invariant Labs; 97 user tasks, 629 security test cases; `pip install agentdojo` | github.com/ethz-spylab/agentdojo, arXiv 2406.13352 |
| Playwright `inner_text()` returns rendered text (skips CSS-hidden); `text_content()` returns textContent (includes it) | Playwright API docs / confirmed by multiple references |
| ShellHacks 2026: Sept 25-27, FIU main campus, ~1,500 students; sponsors incl. Nvidia, Google, Microsoft, Waymo, Assurant; sponsor challenges with prizes; first-time hacker prize | Caplin News (FIU), Sept 2026 |
| Other open-source hidden-text scanners exist (sentinel-security, SafeFetch, stegoff, aiitg, agent-armor) | Their PyPI/GitHub/DEV pages |

## Reported by third parties, NOT verified (don't put on slides as fact)

- Free-tier daily limits (~20/day full Flash, ~500/day Flash-Lite). Check your AI Studio page.
- Any "Black Hat 2026: every AI browser was vulnerable" claim from the earlier draft. Drop it
  unless someone finds the original talk.

- The Zylos / safeguard.sh statistics from the earlier draft.
- The ShellHacks 2025 winners list. Confirm on shellhacks2025.devpost.com before using.

## Not found

- ShellHacks 2026 sponsor challenge list and exact submission deadline: check the hacker
  guide / Devpost at the event.
