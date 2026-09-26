# 07. Benchmark Plan (Role 4, with Role 3)

Goal: numbers a technical judge can't dismiss. Report three separate things and never
blend them into one headline number.

## A. Our hidden-text corpus (label it "our test set")

- 15+ evil pages across the technique table in doc 06, plus 5 rewordings of one payload.
- Metrics: layer-1 detection rate per technique; end-to-end block rate (Shield ON).
- Also report: "unprotected agent fell for X of Y pages" (Shield OFF success rate).

## B. Baseline comparison (the differentiator)

- Run `sentinel-security` (HTML mode) and our layer 1 on the same corpus.
- Output a technique-by-technique table: caught / missed for each.
- `scripts/verify_baseline_gap.py` already does a small version of this without a browser.
- Wording on slides: "On our test pages, a popular open-source scanner missed N of M
  hiding techniques that computed-style rendering caught." Name the version.

## C. Outside datasets for layer 2 (someone else's test set)
Text-only, so they test the judge, not layer 1:

- `deepset/prompt-injections` (Hugging Face): injection vs normal prompts.
- `leolee99/NotInject` (Hugging Face): benign prompts that *contain* trigger words. Good
  for false positives.

- Optional: AgentDojo (ETH Zurich, `pip install agentdojo`): 97 user tasks, 629 security
  cases. Too big to run fully; only mention it if you actually run a slice.

- Budget: 100 samples from each is enough. Use one teammate's key only for this.
- Metrics: precision, recall, F1 for the judge; false-positive rate on NotInject.

## D. False positives on real pages

- 30 benign saved pages through layers 1+2.
- Report: pages with any FLAG, pages with any STRIP/BLOCK, and the top 3 reasons.
- A few FLAGs are fine and honest ("menus and screen-reader text"). BLOCKs on benign
  pages are bugs to fix before judging.

## E. Layer ablation (answers "why three layers?")
Run Shield ON with `SHIELD_LAYERS=3`, `1,3`, and `1,2,3` on both payload families, N runs each,
with the real model. Report the hijack rate per setting and payload. Expected: layer 3 alone stops
exfiltration but not answer manipulation. If the real numbers disagree, report what you got.

## Output format
`benchmark/results/{name}.json` with the raw per-item results and a `summary` block.
`benchmark/results/summary.md` is generated from those files and is the only source for slides.
