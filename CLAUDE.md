# CLAUDE.md: Invisible-Injection Shield (ShellHacks 2026)

You are helping one member of a 4-person team build a hackathon project. Hard deadline: Sunday
Sept 27, 2026, 11:00 AM ET (team target: submitted by 9:00 AM). Clock: `docs/08`.
Before writing any code, read, in order:
1. this file
2. `docs/13_interfaces.md` (the locked contract between the four roles)
3. the task file for the human's role in `tasks/` (ask which role if they didn't say)
4. the docs that task file lists
Each role folder also has its own `CLAUDE.md` with local rules.

## What we are building (one paragraph)
An AI agent browses web pages inside a safe sandbox. Some pages hide instructions that a human
can't see but the AI reads ("indirect prompt injection"). Our shield has three layers:
1. **Visibility gap**: render the page in headless Chromium, use *computed* styles to build a
   "human view", and diff it against the exact text the agent was fed. The difference is stripped.
   Designed to catch external-stylesheet, inherited-color, and alt-text hiding that a source-only
   scanner we tested missed (docs/11). Logic: `shield/gap.py`. Render: `shield/visibility_gap.py`.
2. **LLM judge**: "is this content trying to instruct an AI?"
3. **Action guard**: before email/HTTP/delete, block secrets (Luhn card numbers, key formats,
   reset links, canaries) and confirm unapproved recipients.
Two attack types: exfiltration (email the reset link to the attacker) and answer manipulation (make the
assistant tell the user to enter their password on a phishing site; no tool call, so layer 3 alone can't
stop it). `SHIELD_LAYERS` env var (default `1,2,3`) turns layers off for the ablation benchmark.
Streamlit dashboard: Shield OFF (hijacked) vs Shield ON (stopped, task still done).

## Hard rules
- **Nothing real leaves the sandbox.** Log-only tools stay log-only. No real SMTP, POST, or delete.
- All secrets are fake canaries in `sandbox/fakefs/`. Real API keys only in `.env` (gitignored). Never print keys.
- `contracts/interfaces.py` and `contracts/event.schema.json` are shared. Don't rename or remove
  anything in them. Adding optional fields is OK, but say so in your summary so the human tells the team.
- Stay inside the human's role folder unless their task says otherwise.
- Run `pytest -q` before saying a task is done, and show the acceptance-check output from the task file.
- Numbers for slides come only from `benchmark/results/summary.md`.
- If you're unsure of a library API, inspect the installed package or its docs. Don't guess.
- If a requirement is unclear, stop and ask the human. Don't invent scope. Don't start bonus tasks
  before the task file says so.

## Repo layout
| Path | Owner | What |
|------|-------|------|
| `agent/` | R2 | `llm.py` (Gemini), `loop.py` (`run_agent`), `events.py`, `replay.py` |
| `sandbox/` | R3 | `tools.py` (`execute`, declarations), `fakefs/`, `pages/{evil,benign}/`, `pages/manifest.json` |
| `shield/` | R4 | `action_guard.py` (layer 3), `visibility_gap.py` (layer 1), `judge.py` (layer 2), `pipeline.py`, `policy.json` |
| `frontend/` | R1 | `app.py` (Streamlit) |
| `benchmark/` | R4 | `run.py`, `results/` |
| `contracts/` | all | `interfaces.py`, `event.schema.json`, `sample_events.jsonl` |
| `tasks/` | all | one task file per role, with acceptance checks and Claude Code prompts |
| `docs/` | all | plan, specs, sources. Index: `docs/00_INDEX.md` |

## Status of the starter code
| File | Status |
|------|--------|
| `shield/action_guard.py` | done, tested |
| `sandbox/tools.py` | done, tested (raw mode). Rendered mode TODO (R3-T4) |
| `shield/pipeline.py` | `check_action` done; `check_input` decision logic + ablation tested with a faked render (R4-T2 makes it real) |
| `shield/gap.py` | done, tested: agent view vs human view diff and exact stripping |
| `agent/loop.py` | draft; plumbing tested with a fake model; model errors end the run cleanly; real Gemini call untested (R2-T1) |
| `agent/llm.py` | draft; google-genai type names verified against v2.25.0; never called the API |
| `shield/visibility_gap.py` | ran in real Chromium on all current pages: payload found and stripped on every raw-mode evil page. `tests/test_visibility_gap.py` still to write (R4-T1) |
| `shield/judge.py`, `agent/replay.py`, `frontend/app.py`, `benchmark/run.py` | stubs |

## Commands
```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m playwright install chromium                  # layer 1 and rendered browsing
cp .env.example .env                                   # GEMINI_API_KEY, AGENT_MODEL, JUDGE_MODEL
python scripts/list_models.py                          # pick model ids
pytest -q                                              # must stay green
python -m http.server 8000 -d sandbox/pages            # serve test pages (keep running)
python -m agent.loop --shield off                      # CP1 check
python -m agent.loop --shield on
python -m shield.visibility_gap http://localhost:8000/evil/recipe_external_css.html
python scripts/verify_baseline_gap.py                  # differentiator evidence
streamlit run frontend/app.py
```

## Model / API
Gemini through `google-genai`: agent `gemini-3.8-flash`, judge `gemini-3.5-flash-lite` (pinned in
`.env.example`). Manual function calling (auto-execution disabled), history appended
unchanged (Gemini 3 thought signatures). Model ids come from `.env`, never hardcoded. Free-tier quota
is per project, so each teammate uses their own key. See `docs/03_stack.md`.

## Style
Python 3.11+, type hints, small functions, docstrings on public functions. Prefer boring and reliable.
It's a live demo: nothing on the demo path may raise uncaught exceptions.
