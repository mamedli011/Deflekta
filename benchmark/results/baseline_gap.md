# Differentiator — layer 1 vs the open-source baseline (sentinel-security)

Source for the "what our layer 1 adds over an existing scanner" slide. Generated 2026-09-27 via
`scripts/verify_baseline_gap.py` (run with `PYTHONUTF8=1` on Windows). No API.

"passes" = the payload reaches the model through that converter; "dropped" = the converter removes it.
sentinel-security 0.9.0 (HTML mode): MEDIUM = flagged, CLEAN = missed.

| technique | html2text | markdownify | bs4 | sentinel-security (HTML) |
|-----------|-----------|-------------|-----|--------------------------|
| inline_display_none | passes | passes | passes | MEDIUM `hidden_html` |
| inline_font_size_0 | passes | passes | passes | MEDIUM `hidden_html` |
| internal_css_class_hidden | passes | passes | passes | MEDIUM `css_class_hiding` |
| internal_css_offscreen | passes | passes | passes | MEDIUM `css_class_hiding` |
| **inline_white_on_white** | passes | passes | passes | **CLEAN (missed)** |
| **external_css_class** | passes | passes | passes | **CLEAN (missed)** |
| **inherited_low_contrast** | passes | passes | passes | **CLEAN (missed)** |
| **img_alt** | passes | passes | dropped | **CLEAN (missed)** |
| aria_label | dropped | dropped | dropped | CLEAN |
| html_comment | dropped | dropped | dropped | MEDIUM `hidden_html` |
| visible_plain | passes | passes | passes | CLEAN |

## Verified claim
On our test techniques, sentinel-security reported **4 hiding techniques as CLEAN that still reach the
model**: `inline_white_on_white`, `external_css_class`, `inherited_low_contrast`, `img_alt`. Our layer 1
catches all four because it reads *computed* styles (resolving the full CSS cascade, incl. external
sheets and inherited color) and drops attributes a human never reads (so alt text shows up in the
agent-vs-human diff). This is the honest, reproducible basis for the differentiator on stage.

## Notes (honest)
- `aria_label` and `html_comment` are **dropped** by html2text/markdownify, so they never reach a
  raw-mode agent — not real threats in this pipeline (sentinel flags `html_comment`, but it's moot).
- Techniques sentinel *does* catch (`display_none`, `font_size_0`, CSS-class hiding) are also caught by
  our layer 1 — we do not claim the baseline catches nothing.
- Baseline named/version: sentinel-security 0.9.0, HTML mode. Do not generalize to other scanners.
