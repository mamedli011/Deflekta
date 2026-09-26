# 12. Claude Code Workflow

## Setup (each teammate)

1. Clone the repo, open it in Claude Code from the repo root (so it picks up `CLAUDE.md`).
2. First message in every new session:
   "Read CLAUDE.md, docs/13_interfaces.md and tasks/{my_file}. I'm Role N. Tell me which task is
   next and what 'done' means for it. Don't write code yet."
3. Work on a branch named after your role (`r2-agent`), merge to `main` at checkpoints.

## Rules to give Claude Code if it drifts

- "Stay inside my folder unless the task says otherwise."
- "Don't change contracts/ without asking me."
- "Run pytest before telling me it's done."
- "If you're guessing an API signature, stop and check the installed library or docs."

## Task prompts
Moved into the role task files: `tasks/R1_frontend_pitch.md`, `tasks/R2_agent.md`,
`tasks/R3_sandbox.md`, `tasks/R4_shield_benchmark.md`. Each task has an ID (e.g. R4-T2), a "done
when" check, and a copy-paste Claude Code prompt for the first task.

For later tasks the pattern is: "Do R3-T3. Show me the acceptance check output when finished."

## Before merging
`pytest -q` green, the task's acceptance check passes, and the task box is ticked in the task file.
