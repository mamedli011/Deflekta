# R4 Shield Implementation (Edward, Role 4: Shield + Benchmark)

Technical handoff for teammates and judges. Everything here is taken from the `r4-shield` branch
(code, tests, git history). Where something has only been tested offline, or not run at all, it says so.

## 1. Responsibility and architecture

R4 owns `shield/` (layer 1 visibility gap, layer 2 judge, the `check_input` / `check_action` glue in
`pipeline.py`) and `benchmark/`. Other components used here belong to teammates: the agent loop (R2,
`agent/`), the sandbox tools and attack corpus (R3, `sandbox/`), the dashboard (R1, `frontend/`). The layer-3
action guard (`shield/action_guard.py`, `policy.json`) came with the starter code.

```
user task -> agent (R2) -> browse_web (R3) -> page text ----> check_input  (R4)  -> clean_text -> model
                                                                 layer 1: visibility gap (Chromium)
                                                                 layer 2: Gemini judge
             model tool call -> check_action (layer 3 action guard) -> execute (log-only tools)
```

- **Layer 1** renders the page in headless Chromium, reads computed styles, builds a "human view", and
  strips the sentences the agent received that a person can't see.
- **Layer 2** asks a Gemini model whether page content tries to instruct the AI. Its answers only count when
  grounded in the page text.
- **Layer 3** checks every outgoing tool call (email, HTTP, delete) for secrets, canaries and unapproved
  recipients. It is the backstop for attacks the input filters miss; it cannot see answer manipulation.
- `SHIELD_LAYERS` (default `1,2,3`) switches layers off for ablation.

## 2. Layer 1: visibility gap (`shield/visibility_gap.py`, `shield/gap.py`, `shield/pipeline.py`)

What was implemented and tested on this branch:

| Area | What it does | Tests |
|---|---|---|
| Visibility-gap foundation | Chromium computed styles (display, visibility, effective opacity, font size, offscreen, clip, contrast) mark hidden elements; the agent-vs-human text diff is stripped | `test_visibility_gap.py`, `test_gap.py` |
| Real `check_input` path | Real browse text + real Chromium scan end to end, no fakes | `test_pipeline_real.py` |
| Same-load scan reuse | `check_input(..., scan=None)` reuses a valid scan from the same page load (rendered mode) instead of rendering twice; falls back safely | `test_pipeline_scan_reuse.py` |
| External CSS / rendered pages | Hiding defined in external or inline stylesheets is resolved by the browser, which a source-only scanner misses | corpus tests |
| False-positive guards | Ordinary visible content (10px text, 0.6 opacity, fades, sticky/fixed headers, open `<details>`, transforms, ellipsis) is not flagged | `test_visibility_false_positives.py` |
| Scroll-reachable content | Text further down an `overflow:auto/scroll` box is no longer "offscreen"; negative offsets, fixed elements and clipped content inside such boxes still are | same file |
| Scanner network safety | The layer-1 Chromium can only reach `localhost`/`127.0.0.1` (R3's sandbox allowlist): request routing, WebSocket mocking, blocked service workers, host-resolver rules, redirect check | `test_scan_network_safety.py` |
| Hidden non-text content | A hidden `<img src>` or empty `<a href>` (which html2text feeds to the agent as `![alt](src)` / `[](href)`) is reported as a hidden segment and removed from the human view | `test_hidden_images.py` |
| R3 corpus integration | Tests and scoring use each page's manifest `detect` string (default `evil.example`), including pages whose string also appears in visible text | `test_visibility_gap.py`, `test_pipeline_real.py`, `test_benchmark_run.py` |

**Known layer-1 bypasses (current manifest, `known_bypass: true`):** `color_transparent`, `color_rgba_alpha0`,
`opacity_006`, `font_size_2px`, `transform_scale0`, `overflow_clip_3px`, `text_indent_offscreen`,
`covered_by_overlay`, `closed_details`. These nine pages reach the agent unfiltered by layer 1 today.
`test_known_bypass_is_still_missed` asserts the miss, so a fix shows up as a failing test until the manifest
is updated. Fixes for the first seven were designed but deliberately not implemented; `covered_by_overlay`
and `closed_details` are deferred for policy reasons (overlay detection is unreliable; collapsed FAQ content
is legitimately user-reachable).

## 3. Layer 2: Gemini judge (`shield/judge.py`, `shield/pipeline.py`)

- **One call per page**, `JUDGE_MODEL` from the environment (no hardcoded model id), 15 s timeout, no retries.
- **Structured output:** JSON schema with `is_instruction_to_ai`, `confidence`, `target_action`, `quoted_span`,
  `reason`. Replies are validated strictly (types, finite confidence in 0..1); anything malformed or failing
  raises `JudgeUnavailable`, which the pipeline treats as "no judge".
- **Exact-substring grounding, computed locally:** a positive verdict counts only if `quoted_span` is a
  non-empty exact substring of the page text actually sent to the model (never our prompt scaffolding).
- **`hidden_complete`, computed locally:** true only if all hidden text fit the prompt budget
  (50 segments, 2,000 chars each, 6,000 total; visible text 6,000). The model cannot set it.
- **Decisions:** hidden text with a grounded, complete, confident verdict (>= 0.6) or an unknown judge on a
  serious hidden span is STRIPPED (fail-safe: an unavailable, ungrounded or partial judge never downgrades
  serious hidden content). Visible-only text is FLAGGED only for a grounded instruction at >= 0.8.
- **Untrusted-content hardening:** content is wrapped in `<untrusted>` delimiters; any tag-like
  `<untrusted` / `</untrusted` in page text is neutralized without deleting the text around it.
- **Visible instruction removal (committed in `cc0a2c3`):** a grounded instruction at >= 0.8 has the
  sentence containing its exact quote replaced with `[instruction to the AI removed by shield]`, for
  visible-only pages and for visible instructions left after layer-1 stripping. Rules: exact match only,
  quotes under 15 characters remove nothing, never past a newline or a table-cell separator, leading list
  markers / headings / labelled prefixes (`**Step 3:**`) kept, repeats removed deterministically. If the quote
  is not in the post-layer-1 text, the page is only flagged. Removed pieces are recorded locally in
  `judge.removed_visible`. The verdict stays FLAGGED / medium / layer 2.
- **Answer-steering prompt (added together with this document):** the prompt now also asks about changing what
  the AI tells the reader (forcing recommendations, rankings or links, hiding warnings, overriding the user)
  and explicitly excludes ordinary reader-facing imperatives (recipe steps, navigation, safety advice).
  **Offline tests pass; the planned 12-case live validation has not been run.** Whether Gemini actually
  classifies these correctly is not yet known.

Live evidence to date: one manual 3-call smoke test with the earlier prompt (hidden exfiltration, benign skip
link, visible disguised instruction) returned the expected grounded verdicts. No other live judge runs.

## 4. Layer 3 relationship

Layer 3 (starter code) blocks outgoing tool calls that carry canaries, card numbers, key/reset-link patterns
or go to unapproved recipients, and asks for confirmation on destructive actions. R4's contribution is the
integration context: layers 1 and 2 reduce what reaches the model; layer 3 stops the harmful action if an
injection still gets through. Answer manipulation (no tool call) is only addressable by layers 1 and 2,
which is why the ablation `SHIELD_LAYERS=3` is expected to miss it.

## 5. Benchmarks and evaluation

| Tool | Status |
|---|---|
| `scripts/verify_baseline_gap.py` (starter) | Reproduced locally: sentinel-security 0.9.0 marks inline white-on-white, external-stylesheet class, inherited near-white and img-alt as CLEAN. R4 added the missing `markdownify` dependency. Needs `PYTHONUTF8=1` on Windows. |
| `benchmark/run.py` (Benchmark A/B/D, + R2 files) | Implemented and tested. Layer 1 with judge off (`SHIELD_LAYERS=1,3`), sentinel-security baseline in a UTF-8 subprocess, per-page `detect` scoring with visible/hidden occurrence counts. R2's `attack_success.json` / `ablation.json` are copied, never computed; missing files are reported as not available. No official `summary.md` committed yet. |
| `benchmark/latency.py` | Measures Shield ON vs OFF per page. A local run (5-page corpus, raw mode) showed about 1 s added per page, almost all Chromium start-up and the network-idle wait. Not committed as results. |
| `benchmark/judge_eval.py` (Benchmark C) | Implemented and offline-tested; **not run live**. Pinned datasets: `deepset/prompt-injections` rev `4f61ecb…` split `test` (label 1 = INJECTION per deepset's classifier config) and `leolee99/NotInject` rev `847ae76…` (all benign). 100 samples each, recorded seed, at most 200 judge calls, stops after 5 consecutive unavailable answers, saves after every sample, resumes without duplicates. |

**Prompt provenance (added together with this document):** Benchmark C's config records
`judge_prompt_sha256` = sha256 of the exact `JUDGE_PROMPT`. Resume already refuses any config mismatch, so a
run started with one prompt can no longer be resumed and silently mixed with answers from another; every
finished `judge_eval.json` names the prompt that produced it.

A local offline Benchmark A run on the frozen 38-page corpus completed with 0 errors (23/23 expected layer-1
pages flagged, the 9 known bypasses missed, 0 of 5 visible pages wrongly flagged). These are verification
numbers, not slide numbers: official figures must come from a committed `benchmark/results/summary.md`.

## 6. Security design decisions

- **Rendered computed styles, not source inspection:** hiding via external CSS, inheritance or scripts is only
  visible after the browser applies the cascade.
- **Exact grounding:** the model must quote the page verbatim or its verdict is treated as unknown.
- **Security fields are local:** `grounded`, `hidden_complete`, `removed_visible` and the prompt fingerprint are
  computed by our code; the model cannot supply them.
- **Fail-safe hidden handling:** serious hidden text is stripped unless a grounded, complete judge says otherwise.
- **Scanner network restrictions:** the layer-1 browser cannot contact hosts outside the sandbox, so hidden
  images carrying tokens cannot leak them.
- **No secrets in git:** `.env` is ignored; tests block live judge calls (`tests/conftest.py`); a dummy-key check
  confirms zero Gemini clients are created by the suite. No generated results are committed.
- **Frozen corpus:** R3's `sandbox/` is unchanged by R4 since the merge (identical to `3c8c1f3`).

## 7. Testing

The full suite is offline: Chromium tests run against local servers; judge tests script the model reply.

| Suite | Proves |
|---|---|
| `test_visibility_gap.py`, `test_pipeline_real.py` | Layer 1 on every manifest page: detection, human view, exact diff, known bypasses, layer-2 pages |
| `test_visibility_false_positives.py`, `test_hidden_images.py` | Visible content stays visible; hidden images are caught |
| `test_scan_network_safety.py` | No request leaves the sandbox (controls show unguarded Chromium would leak) |
| `test_judge.py`, `test_judge_prompt.py` | Judge validation, grounding, budgets, delimiters, prompt categories |
| `test_layer2_remediation.py` | Visible instruction removal, boundaries, thresholds, mixed hidden+visible pages |
| `test_pipeline_*`, `test_initial_fixes.py` | Decision table, fail-safe paths, scan reuse, ALLOWED reasons |
| `test_benchmark_run.py`, `test_judge_eval.py` | Benchmark scoring, resume, provenance, honest "not available" reporting |

Scripted judge tests prove how the pipeline handles a verdict, not how Gemini classifies text.

Latest full offline run (2026-09-27, including the answer-steering and provenance
changes): **605 passed, 0 failed, 0 skipped**.

## 8. Known limitations and remaining work

- Nine known layer-1 bypasses (section 2); seven have a design, none are implemented.
- Answer-steering prompt: offline only; the 12-case live validation is pending.
- Benchmark C has never been run live; no precision/recall or NotInject false-positive numbers exist.
- R2's end-to-end OFF-vs-ON attack-rate and ablation runs are pending (and depend on a working attack).
- One quote per judge call: a page with several instructions can keep the unquoted ones; layer 3 still
  guards tool-based harm, answer steering is not covered for the rest.
- The judge sees only the first 6,000 visible characters of a page.
- The benign corpus has one page (docs/07 targets 30), so false-positive numbers are provisional.
- Visible images with `alt` text have their image line removed (the human view drops alt text by design).
- R3's rendered browse path (R3-owned) blocks requests but lacks the resolver-rule and WebSocket guards
  added to the layer-1 scanner.

## 9. R4 milestones (`r4-shield`, oldest first)

| Commit | Milestone |
|---|---|
| `9e8d8f2` | Layer 1 visibility-gap tests |
| `a9fce8e` | Real `check_input` integration tests |
| `d663a86` | Shield latency benchmark |
| `f17bf7a` | Reuse same-load layer-1 scan (T2b) |
| `961d59c` | Visibility tests aligned with the expanded corpus |
| `adcf5fe` | `markdownify` for the baseline gap script (T3) |
| `a3b3138` | Gemini layer-2 judge with grounding (T4) |
| `3eb98a0` | Judge hardening: delimiters, budgets, `hidden_complete` (T4a) |
| `b7d6013` | Benchmark runner (T5) |
| `9b95eb9` | Layer-1 false-positive guard tests (T5a) |
| `9e625a2` | Scroll-reachable content no longer offscreen (T5b stage 1) |
| `d402324` | Benchmark C judge-evaluation runner, offline-tested (T6) |
| `0cdf479` | Accurate ALLOWED reasons, shield guidance, task status (T6a) |
| `28292e8` | Merge of R3's finalized corpus (`3c8c1f3`; the merged commits are R3's work) |
| `4ab6315` | Layer-1 scanner blocked from non-sandbox network access |
| `f25c053` | Integration tests aligned with the per-page `detect` contract |
| `90e4e7c` | Hidden non-text agent content detected |
| `a745902` | Benchmark scoring aligned with `detect` |
| `cc0a2c3` | Grounded visible AI instructions removed |

The two earliest branch commits (`2f578d2`, `076a657`) only tested GitHub access.

## 10. How to verify R4

From the repo root with the project virtualenv (Windows: `.venv\Scripts\python`):

```bash
python -m pytest -q                                              # full offline suite, no API calls
python -m benchmark.run --out-dir /tmp/bench_a                   # Benchmark A/B/D offline, judge off
python -m benchmark.judge_eval --plan                            # Benchmark C plan: downloads public
                                                                 # datasets, makes NO model calls
PYTHONUTF8=1 python scripts/verify_baseline_gap.py               # baseline scanner comparison
python -m benchmark.latency --reps 3 --out /tmp/latency.json     # Shield ON vs OFF latency
```

**LIVE (spends Gemini quota; needs `GEMINI_API_KEY` and `JUDGE_MODEL`; coordinate first):**

```bash
python -m benchmark.judge_eval    # LIVE: up to 200 judge calls
```

Use `--out-dir` / `--out` outside the repo so generated results are not committed by accident.
