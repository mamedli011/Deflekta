# 01. Project Brief

## One-liner
Websites can secretly give orders to AI agents. We built a shield that sees what the
human can't, and stops the agent before it acts on it.

## Problem
AI assistants now read web pages, email, and documents and then take actions
(send email, fill forms, make requests). They cannot reliably tell *content they are
reading* apart from *instructions they should follow*. An attacker can hide a
sentence in a page (CSS-hidden, white-on-white, tiny font, off-screen) that humans
never see, but the agent reads and may obey. This is indirect prompt injection,
listed as LLM01 (Prompt Injection) in the OWASP Top 10 for LLM Applications (2025).
When the agent has tools, it becomes LLM06 (Excessive Agency) territory as well.

## Human story (pitch version)
Someone asks their AI browser, which is signed into their email, to find a pasta
recipe. The recipe page hides one sentence: forward the newest account-recovery
email to an outside address. The AI does it. The person never sees anything.
Our shield shows them exactly what the page hid, and blocks the email.

## Solution: three layers

| Layer | Question it answers | Why it matters |
|------|---------------------|----------------|
| 1. Visibility gap | "What can the agent read that a human can't see?" | Independent of wording. Rewording the attack does not beat it. |
| 2. LLM judge | "Is this content trying to instruct an AI?" | Catches visible or disguised instructions layer 1 can't. |
| 3. Action guard | "Is this action about to leak a secret or contact an unapproved party?" | Last line of defense, works even if 1 and 2 miss. |

## Prior art we must acknowledge (found Sept 26)
- **PhantomLint** (arXiv 2508.17884, 2025) renders HTML with Playwright and compares rendered text with
  extracted text to find hidden prompts. It targets documents (papers, CVs), not live agent tools.
- **Prompt-Injector-Detector** (public GitHub project) advertises a "human-visible rendered view vs
  AI raw stream view" comparator with a Gemini judge. Judges may know it.
- **BrowseSafe** (Perplexity, arXiv 2511.20597) finds detectors do well on hidden HTML and worse on
  visible, rewritten attacks. So layer 1's value is being deterministic, cheap and explainable, and our
  ablation has to show what it adds over the judge alone.
So the *idea* of comparing views is not ours. What is ours: doing it inline inside an agent's browsing
tool, on the exact string the model receives, combined with a grounded judge and an action guard, and
measured with an ablation.

## Honest differentiator (verified, see doc 11)
Hidden-text scanning for AI agents is NOT new. Several open-source tools already do it
(for example sentinel-security, SafeFetch, stegoff, aiitg, agent-armor). Do not claim
to be first.

What we can claim and prove: at least some of these scanners work on the raw HTML
source (stegoff's README describes style-attribute regex; sentinel-security we tested
ourselves). We have NOT checked how SafeFetch, aiitg, or agent-armor work internally,
so never say "all existing tools" on a slide. We render the page in a real browser and read
**computed** styles. We ran sentinel-security 0.9.0 (HTML mode) on our own test pages
with a reworded injection. It flagged inline `display:none`, `font-size:0`, and hiding via
classes in an inline `<style>` block, but reported CLEAN for these, all of which still reached the model through html2text:

- white text on a white background set via inline styles,
- a class defined in an **external** stylesheet,
- near-white text **inherited** from a parent's class,
- instructions in image **alt text**, which html2text and markdownify pass to the model.

Our layer 1 is designed to catch all four (the diff logic is tested; confirm the real
browser run in R4-T1 before saying it on stage): the first three because computed styles resolve the whole CSS
cascade, and alt text because our "human view" drops attributes a person never reads, so alt text
shows up in the difference between the two views. That is our live demo moment and our
answer to "how is this different?"

Pitch wording that is true: "Comparing what a browser draws with what a parser extracts has been
done for documents (PhantomLint, 2025). We put it inside an AI agent's browsing tool, diff the exact
text the model receives, back it with a grounded judge and an action guard, and measured what each
layer adds. In our test, the open-source scanner sentinel-security 0.9.0 reported four hiding
techniques as clean while html2text still fed them to the model."

## Why three layers (two attack types)
1. **Exfiltration**: hidden text tells the agent to email the password-reset link to the attacker.
   The action guard (layer 3) alone would block this, because it recognizes reset links.
2. **Answer manipulation**: hidden text tells the agent to tell the user their recipes will be
   deleted unless they "confirm their password" at a phishing link. There is no tool call, so
   layer 3 never sees it. Only layers 1 and 2 stop it.
Our tests already show this with a simulated gullible model: with only layer 3 on, attack 2 still
succeeds; with all layers on, it doesn't. The benchmark repeats that with the real model.

## Scope
In: sandbox agent, 3 layers, dashboard, benchmark with honest numbers, one real hosted page.
Out (bonus only after checkpoint 3): Chrome extension, attacker-AI generator, PDF/image injections.

## Success criteria
See `00_INDEX.md`, "five things that must be true at judging".
