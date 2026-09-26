# 10. Risks and Judge Q&A

## Risks

| # | Risk | Severity | Mitigation |
|---|------|----------|------------|
| 1 | Model refuses the injection in Shield OFF mode | High | Test at CP1. Try Flash-Lite variants and payload wording. Cache a successful run. Disclose config. |
| 2 | Layer 1 breaks on real pages (timeouts, heavy JS) | High | 10 s timeout, fall back to static checks and mark `render_failed`. Test on benign corpus early. |
| 3 | Free-tier quota runs out mid-demo | High | Per-person projects, benchmark on its own key, replay mode, backup video. |
| 4 | "It's all fake" | Medium | One hosted evil page fetched live over real HTTP; `wrap_tools` around a second setup if time. |
| 5 | "How is this different?" | Medium | Baseline-gap table (doc 07 B). Never claim "first". |
| 6 | False positives on real sites | Medium | Graded verdicts (FLAG vs STRIP vs BLOCK), measured on 30 pages. |
| 7 | Integration hell | Medium | Contract frozen at hour 1, first ugly end-to-end run by CP2. |
| 8 | Scope creep | Medium | Cut list in doc 08. Bonus list opens only after CP3. |
| 9 | A cited statistic is wrong | Medium | Only doc-11 verified sources on slides. |

## Judge Q&A
**How is this different from Prompt Shields / Model Armor / existing scanners?**
Text classifiers judge what words say. Source-level scanners read the HTML. We render the
page and compare what a browser draws with what the AI is fed, then guard actions. On our
test pages, a popular open-source scanner missed [N] hiding techniques we caught. A cloud
classifier could plug in as our layer 2.

**Hasn't this been done? (PhantomLint, Prompt-Injector-Detector)**
Yes, the render-vs-extract idea exists, and we credit it. PhantomLint scans documents. We run the
comparison inside the agent's own browsing tool on the exact text the model gets, strip only the gap,
add a grounded judge and an action guard, and show an ablation of what each layer adds.

**Isn't the browser rigged to feed hidden text to the agent?**
No. We used html2text, a common HTML-to-text converter. We checked: it passes
`display:none` text, white-on-white text, and alt text straight to the model.

**If layer 3 already blocks the email, why do you need layers 1 and 2?**
Because not every attack sends anything. When the page makes the AI tell the user to "confirm
their password" at a phishing link, there's no tool call for layer 3 to inspect. Our ablation:
[layer 3 only: X of Y hijacked; all layers: Z of Y].

**What if the attacker doesn't hide the text?**
Layer 2 catches visible instructions, and layer 3 stops the dangerous action regardless.

**Canary tokens don't exist in real life. How does layer 3 protect real users?**
Canaries are our test oracle. Real protection is Luhn-validated card detection, known
secret formats, reset-link detection, and a recipient allowlist with human confirmation.

**What about false positives? Real sites hide text.**
Hidden text alone is a warning, not a block. Measured on 30 real pages: [numbers].

**Can it be bypassed?**
Yes, no single defense is perfect. Examples: instructions inside images, or text that's
visible but disguised. That's why there are three independent layers, and why the action
guard doesn't depend on detection at all.

**Who would use this?**
Teams building agents (as a library wrapper) and people using AI browsers (as an extension,
next step).
