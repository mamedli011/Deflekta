# 09. Demo and Pitch (about 2 minutes)

| Time | Screen | Say (rough) |
|------|--------|-------------|
| 0:00 | Title + human story | "Someone asks their AI browser, signed into their email, for a pasta recipe. The page hides one sentence." |
| 0:20 | Shield OFF run | "Watch the agent read the page, open the inbox, and forward the account-recovery email to a stranger. The human saw nothing." |
| 0:45 | Human view vs AI view (or detail panel) | "This is what the page hid. It's set in an external stylesheet, which is why the open-source scanner we tested reported this page as clean (if you re-ran it on this exact page)." |
| 1:05 | Shield ON, same task, same page | "Layer 1 finds text a browser never draws. Layer 2 confirms it's an instruction. Layer 3 would block the email anyway. And the recipe still arrives." |
| 1:20 | Ablation (one slide or a second quick run) | "Why three layers? Here the page doesn't steal anything. It makes the AI tell you to 'confirm your password' on a phishing site. No email is sent, so an action guard alone never sees it. Layer 1 does." |
| 1:30 | Scorecard from `benchmark/results/summary.md` | "On our test set, X of Y attacks stopped, and on 30 real pages, Z blocks. Here's how that compares to a source-only scanner." |
| 1:50 | Close | "AI agents read the page the attacker wrote. We check it against the page the human sees, inside the agent, before it acts." |

## Tracks to enter (confirm official 2026 wording on Devpost first)
- Best Overall (automatic).
- MLH Best Use of Gemini API, if offered (Gemini is the agent and the judge).
- Assurant's AI track (reported as "Take Control of AI"), if the wording fits.
- First-time hacker prize only if at least half the team are first-timers (2025 rule).
- Skip: Google Cloud agent track (2025 required ADK/A2A), Microsoft (reported "cannot be a chatbot"),
  Waymo, Sperry, Nvidia.

## Citations usable on slides (verified Sept 26)
- Brave (Aug 2025): Perplexity Comet followed hidden page instructions and leaked the user's email and OTP.
- Brave (Oct 21, 2025): indirect prompt injection is "a systemic challenge facing the entire category of
  AI-powered browsers."
- OpenAI (Dec 22, 2025): prompt injection is "unlikely to ever be fully 'solved.'"
- WASP benchmark (arXiv 2504.18575): attacks partially succeed in up to 86% of cases.
- Forcepoint X-Labs (Apr 2026): 10 verified in-the-wild hidden prompt injections, including white-on-white
  1px text.
- Unit 42 (Palo Alto Networks): web-based indirect prompt injection observed in the wild.
- Prior art to credit: PhantomLint (arXiv 2508.17884).

## Slide rules

- Every number comes from `benchmark/results/`. Say which test set it came from.
- Only say "the scanner reported this page as clean" after running the baseline on that exact demo page.
- Cite only sources listed as verified in doc 11.
- Never say "first", "only", or "all existing tools".
- If the Shield OFF run needed a weaker model or a specific prompt, say so in one line.

## Devpost checklist
Problem, solution, how it works (the three layers), the baseline-gap table, benchmark
numbers with test-set labels, demo video, screenshots, public repo with README, sponsor
challenges selected, all teammates added.
