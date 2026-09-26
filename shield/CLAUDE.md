# shield/ (Role 4)
Task list: `tasks/R4_shield_benchmark.md`. Interfaces: `check_action(tool, args) -> ActionDecision`,
`check_input(url, page_text, raw_html=None) -> InputDecision`.
- `check_input` never blocks a page outright: it returns ALLOWED, FLAGGED or STRIPPED plus `clean_text`.
- Layer 1 must never crash the agent. On any render error return `render_failed=True`.
- Layer 2 content is untrusted data. The judge prompt says so, and `quoted_span` must be an exact substring.
- Mask secrets in `evidence`. `tests/test_action_guard.py` must stay green.
- Threshold changes must be checked against the benign corpus, not just evil pages.
