# 03. Stack

| Area | Choice | Why |
|------|--------|-----|
| Language | Python 3.11+ | Whole team can read it; all libs available. |
| LLM | Gemini via `google-genai` SDK | Google is a ShellHacks 2026 sponsor; free tier needs no card; supports function calling and structured JSON output. |
| Rendering | Playwright (Chromium, headless) | Computed styles, real CSS cascade, JS-injected content. |
| HTML parsing | BeautifulSoup4 | Comments, attributes, fallback static checks. |
| Page-to-text for agent | html2text | Realistic: common converter, verified to pass hidden text through. |
| UI | Streamlit | Fastest path to a live dashboard in Python. |
| Tests | pytest | Action guard already tested. |
| Hosting (1 evil page) | GitHub Pages | Free, 10 minutes, answers "it's all fake". |

## Model choice and quota strategy (read this before coding the agent)

- Google's official rate-limit page (updated 2026-09-02) says limits are **per project,
  not per API key**, and daily quotas reset at midnight Pacific. Exact numbers are shown
  per account in AI Studio, not in the docs.

- Third-party summaries from September 2026 report the free tier for the full Flash
  models at roughly **20 requests/day**, and Flash-Lite models at roughly **500/day**.
  Treat those as unverified until you check your own AI Studio rate-limit page.

- **Pinned (from ai.google.dev, Sept 26, 2026):** agent `gemini-3.8-flash` (GA), judge
  `gemini-3.5-flash-lite` (fallback `gemini-3.1-flash-lite`). Google's models page says new projects
  should use these two. The 3.1 Flash-Lite *Preview* was shut down May 25, 2026.
- **3.8 Flash migration rules** (already applied in `agent/llm.py`): don't set temperature/top_p/top_k;
  use `thinking_level` (we use `low`; `minimal` isn't supported); every FunctionResponse carries the
  call's `id` and `name`.
- Exact free-tier RPM/RPD isn't in the docs anymore. Read it on AI Studio's rate-limit page and post it
  in the team chat before R2-T5 / R4-T5 budget their runs.
- An agent run is several model calls, and the benchmark is hundreds. So:
  - `AGENT_MODEL` = `gemini-3.8-flash`. If quota runs out or it resists the injection at CP1, try
    `gemini-3.5-flash-lite` as the agent and say so in the pitch.
  - `JUDGE_MODEL` = `gemini-3.5-flash-lite`, structured JSON output
    (`response_mime_type="application/json"` + `response_json_schema`).
  - **Each teammate creates their own AI Studio project/key.** Quotas are per project,
    so four people means four quotas. Assign one key to the benchmark only.
  - If someone can add billing, Tier 1 removes most pain. Not required.
- Get exact model IDs with `python scripts/list_models.py`. Do not trust IDs from blog
  posts. At time of writing, the docs' top banner mentioned `gemini-3.8-flash`, and the
  official batch table listed Gemini 3.5 Flash-Lite and 3.1 Flash Lite.

- Gemini 3 models use "thought signatures" in function calling. When you send history
  back, append the model's returned `content` object unchanged instead of rebuilding
  it by hand. (The docs have a "Thought signatures" page; skim it.)

- Google now labels `generate_content` as the "Generate Content API (Legacy)" next to a newer
  Interactions API. `generate_content` still works and has the most examples, so we use it.
  Don't switch mid-hackathon.
- Fallback provider: the Gemini API has an OpenAI-compatibility endpoint, so switching
  to another provider later is a client change, not a rewrite.

## Versions verified in the planning environment

| Package | Version tested |
|---------|----------------|
| Python | 3.12.3 |
| beautifulsoup4 | 4.14.3 |
| html2text | 2025.4.15 |
| markdownify | 1.2.2 |
| sentinel-security (baseline, benchmark only) | 0.9.0 |
| google-genai | 2.25.0 (type names used in `agent/llm.py` verified to exist; no live API call made) |
| requests | installed, used by `browse_web` |

Playwright (with Chromium) and streamlit were not available in the planning environment.
Pin whatever versions install cleanly on your machines into `requirements.txt`.
