# frontend/ (Role 1)
Task list: `tasks/R1_frontend_pitch.md`. Reads `runs/*.jsonl` (format: `contracts/event.schema.json`),
calls `agent.loop.run_agent`, and `agent.replay.replay`.
- Colors: ALLOWED green; FLAGGED, NEEDS_CONFIRM yellow; STRIPPED, BLOCKED red.
- Never hardcode benchmark numbers. Read `benchmark/results/summary.md`.
- Replay mode must work with no network and no API key. That is our demo fallback.
