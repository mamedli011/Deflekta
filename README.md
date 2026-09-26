# Invisible-Injection Shield

ShellHacks 2026 project. A shield that catches instructions hidden in web pages before an
AI agent acts on them, by comparing what a browser actually draws with what the AI is fed.

- Start here: `CLAUDE.md`, then `docs/00_INDEX.md`
- Evidence for our differentiator: `python scripts/verify_baseline_gap.py` (see `docs/11`)
- Tests: `pytest -q`

Safety: everything runs in a sandbox. Email, HTTP, and delete tools only write to a log.
All secrets are fake canaries. Domains used for attacks are reserved `.example` / `.test` names.
