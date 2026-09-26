# 14. Team Workflow

## Kickoff meeting (15 minutes, everyone, before anyone codes)
Agenda (thanks to the teammate who drafted this checklist):
1. **Deadline.** Sunday 11:00 AM ET (doc 08 has the clock). Ask an organizer: is that the Devpost cutoff
   or end of hacking? Also ask: team size limit, video requirement, and whether AI coding tools must be disclosed.
2. **Architecture.** Walk through doc 13's call graph out loud. Everyone must understand that
   the input shield runs on `browse_web` results inside the loop.
3. **Roles.** Confirm who is R1 (UI + pitch), R2 (agent), R3 (sandbox), R4 (shield + benchmark).
   Write names in the table below.
4. **Interfaces.** Accept `contracts/interfaces.py` as-is, or change names now. After this
   meeting, changes need the whole team.
5. **Event format.** Accept `contracts/event.schema.json` and the allowed values in doc 13.
6. **MVP demo.** Recipe page with hidden instruction; Shield OFF forwards the password-reset
   email to the attacker; Shield ON blocks it and the recipe still gets emailed to the user.
7. **Model/API.** `gemini-3.8-flash` (agent) and `gemini-3.5-flash-lite` (judge). Each person creates their own AI Studio key now (quotas are
   per project). R2 runs `python -m agent.llm` before the meeting ends if possible.
8. **Repo.** One GitHub repo, `main` protected by habit: only merge when tests pass.

| Role | Name | Task file |
|------|------|-----------|
| R1 UI + Pitch | | `tasks/R1_frontend_pitch.md` |
| R2 Agent | | `tasks/R2_agent.md` |
| R3 Sandbox | | `tasks/R3_sandbox.md` |
| R4 Shield | | `tasks/R4_shield_benchmark.md` |

## Git workflow
- Branch per role: `r1-ui`, `r2-agent`, `r3-sandbox`, `r4-shield`.
- Stay inside your folder. Shared files (`contracts/`, `CLAUDE.md`, `docs/`) change only after a team OK.
- Merge to `main` at least at every checkpoint, and any time you finish a task:
  `git pull origin main` into your branch, `pytest -q`, then merge.
- Commit small and often. Message format: `R3: add 5 evil pages (offscreen, alt, js)`.
- If `pytest -q` fails on `main`, whoever broke it fixes it before doing anything else.

## Working with Claude Code
- Open Claude Code at the repo root. It reads the root `CLAUDE.md` automatically, and each role
  folder has its own `CLAUDE.md` with local rules.
- First message every session: "Read CLAUDE.md, docs/13_interfaces.md and tasks/{your_file}.
  Tell me which task is next and what 'done' means for it. Don't write code yet."
- Then give it one task ID at a time, e.g. "Do R3-T2." Each task has acceptance checks; ask
  Claude Code to run them and show you the output before you mark it done.
- Tick tasks in your task file (`- [x]`) and commit that too, so the team can see progress.

## Integration order (why the stubs matter)
Every interface already returns valid data, so nobody waits on anyone:
- R1 builds the UI on `contracts/sample_events.jsonl`, then on real `runs/*.jsonl`.
- R2's loop already works with the stub `check_input` and the real `execute`.
- R4 swaps the stub body of `check_input` for real layers without changing its signature.
- R3 adds pages; the loop and benchmark pick them up from `manifest.json`.

## Syncs (5 minutes, standing)
At CP1, CP2, CP3 and feature freeze (doc 08). Each person answers: done, next, blocked.
Blocked for more than 30 minutes means ask for help immediately, not at the next sync.

## Definition of done (any task)
1. Acceptance checks in the task file pass. 2. `pytest -q` green. 3. Merged to `main`.
4. No secret, key, or real outbound side effect added.
