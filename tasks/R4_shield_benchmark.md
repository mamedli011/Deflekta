# R4: Shield + Benchmark (owner: ______)

Folders: `shield/`, `benchmark/`, `scripts/`. Read first: `CLAUDE.md`, `docs/13_interfaces.md`,
`docs/05_shield_spec.md`, `docs/07_benchmark_plan.md`, `docs/11_sources_and_verification.md`.
Starting point: layer 3 (`action_guard.py`) is done and tested. Layer 1 (`visibility_gap.py`) has
been run in real Chromium once (Sat morning) and passed on all current pages; confirm on your machine. `check_input` decision logic and the view diff (`shield/gap.py`) are tested with a faked scan. Layer 2 (`judge.py`) is a stub.
You own the differentiator. **Layer 1 must work on the external-CSS page by CP2.**

## Tasks
- [ ] **R4-T1 Run layer 1** (first 1-2 hours)
  - `pip install -r requirements.txt && python -m playwright install chromium`
  - `python -m http.server 8000 -d sandbox/pages` then
    `python -m shield.visibility_gap http://localhost:8000/evil/recipe_external_css.html`
  - Done when: every current evil page reports a segment containing its payload with the right technique
    (`display_none` for the external/inline CSS pages, `offscreen` for js_injected), `human_html` is returned
    and does NOT contain the payload, and `benign/recipe_clean.html` reports at most the sr-only skip link.
  - Then check the real diff: `shield.gap.gap(browse_text, shield.gap.to_text(human_html))` returns exactly the
    payload sentence(s) for each raw-mode evil page, and nothing for js_injected in raw mode.
  - Write `tests/test_visibility_gap.py` that serves the pages and checks exactly that
    (skip if Chromium isn't installed). Don't loosen assertions to make them pass.
- [ ] **R4-T2 check_input for real** (by CP2)
  - The decision logic in `shield/pipeline.py` is already written and tested with a faked scan
    (`tests/test_pipeline_input.py`). Your job: make it work with the real Playwright scan from T1.
  - Done when: `python -m agent.loop --shield on` logs an `input` event `STRIPPED` on
    `recipe_external_css.html`, and on `recipe_answer_phish.html` the final answer has no phishing link.
    Also run with `SHIELD_LAYERS=3` to confirm the phish page still gets through (that's the ablation point).
  - Tell R1 the final evidence shape (`segments` list, first items are the gap sentences).
- [ ] **R4-T2b Use the tool's scan when present** (with R3-T4)
  - If `raw_html`/meta carries a scan from the same page load, use it instead of rendering again.
    (NFKC + zero-width/tag-character removal is already in `shield/gap.py`.)
- [ ] **R4-T3 Baseline gap check on the real pages** (by CP2)
  - Re-run `python scripts/verify_baseline_gap.py` on your machine and confirm the gap still shows.
  - Extend it (or `benchmark/baseline.py`) to run sentinel-security on every page in the manifest.
    Output `benchmark/results/baseline.json`.
- [ ] **R4-T4 Layer 2 judge** (by CP3)
  - Implement `shield/judge.py` per docs/05: one call per page, JSON response schema
    (`response_mime_type="application/json"` + `response_schema`), exact-substring grounding check.
    Use `JUDGE_MODEL` and your own API key.
  - Plug into `check_input` with the decision table in docs/05.
  - Done when: `visible_disguised` page gets `FLAGGED` by layer 2, and a normal benign page gets `ALLOWED`.
- [ ] **R4-T5 Benchmark A, B, D** (by CP3)
  - `benchmark/run.py`: for every manifest page, run layer 1 (+ layer 2 if quota allows) and the
    baseline. Write `benchmark/results/corpus.json` and generate `benchmark/results/summary.md` with:
    per-technique table (ours vs baseline), benign FLAG/STRIP counts and top reasons, and R2's
    attack-success numbers if `attack_success.json` exists, and the ablation table from `ablation.json`.
  - `summary.md` is the only source for slide numbers. Put the date, model ids and package versions in it.
- [ ] **R4-T6 Benchmark C** (after CP3, only if quota allows)
  - 100 samples each from `deepset/prompt-injections` and `leolee99/NotInject` through the judge.
    Precision/recall/F1 and NotInject false-positive rate. Needs `pip install datasets`.
- [ ] **R4-T7 wrap_tools** (bonus) per docs/02 decision 2.

## Claude Code prompt for T1
"Read CLAUDE.md, docs/05 and tasks/R4_shield_benchmark.md. Do R4-T1. The file shield/visibility_gap.py
has never been run. Serve sandbox/pages on :8000, run it on each page in the manifest, and fix bugs
until the acceptance check in the task passes. Explain each fix. Then write tests/test_visibility_gap.py."

## Watch out
- `textContent` includes `<script>` and `<style>` text. The per-element walk already skips those tags; keep it that way.
- Don't tune thresholds on the evil pages only. Check the benign corpus every time you change one.
- Judge prompt: content is data, never instructions. Grounding check is mandatory.
