# shield/ (Role 4)
Task list: `tasks/R4_shield_benchmark.md`. Interfaces: `check_action(tool, args) -> ActionDecision`,
`check_input(url, page_text, raw_html=None, scan=None) -> InputDecision` (`scan`: optional same-load layer-1
scan from `browse_web` rendered mode; reused only if it is for this exact URL and did not fail).
- `check_input` never blocks a page outright: it returns ALLOWED, FLAGGED or STRIPPED plus `clean_text`.
- Layer 1 must never crash the agent. On any render error return `render_failed=True`.
- Layer 2 content is untrusted data. The judge prompt says so, and `quoted_span` must be an exact substring.
- Judge verdicts count for decisions only if `grounded` is true (computed locally, never taken from the model).
  For hidden-text decisions they must also have `hidden_complete` true. Anything else counts as "no judge".
- Judge config: `JUDGE_MODEL` and `GEMINI_API_KEY` from the environment (`.env`, loaded by the caller; `judge.py`
  does not load it). Missing config, errors and bad output raise `JudgeUnavailable`; `check_input` then falls back.
- Tests: `tests/conftest.py` blocks live judge calls in the whole suite. Script `shield.judge._generate` with
  monkeypatch to test judge behavior; never make live Gemini calls from pytest.
- Mask secrets in `evidence`. `tests/test_action_guard.py` must stay green.
- Threshold changes must be checked against the benign corpus, not just evil pages.
