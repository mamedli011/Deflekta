# Invisible-Injection Shield: Plan Index

Status: living plan. Anything here can change if testing shows a better path.
Last updated: Saturday Sept 26, 2026 (during ShellHacks).

| # | File | Read it if you are... |
|---|------|------------------------|
| 01 | `01_project_brief.md` | Everyone. The what, why, and our honest differentiator. |
| 02 | `02_architecture.md` | Everyone. Data flow and components. |
| 03 | `03_stack.md` | Everyone at setup. Versions, model choice, quotas. |
| 04 | `04_data_contracts.md` | Everyone. Event and policy formats. |
| 05 | `05_shield_spec.md` | Role 4 (Shield). Detailed algorithms and thresholds. |
| 06 | `06_agent_and_sandbox_spec.md` | Roles 2 and 3. Agent loop, tools, canaries, pages. |
| 07 | `07_benchmark_plan.md` | Role 4 (+3). What we measure and how. |
| 08 | `08_roles_and_timeline.md` | Everyone. Who does what, when. |
| 09 | `09_demo_and_pitch.md` | Role 1 (Pitch). Script and slides. |
| 10 | `10_risks_and_judge_qa.md` | Everyone before judging. |
| 11 | `11_sources_and_verification.md` | Anyone making a claim on a slide. |
| 12 | `12_claude_code_workflow.md` | Anyone using Claude Code. How to run sessions. |
| 13 | `13_interfaces.md` | Everyone. The locked function signatures and types. |
| 14 | `14_team_workflow.md` | Everyone. Kickoff meeting, git, syncs, definition of done. |
| - | `../tasks/R1..R4_*.md` | Your personal task list with acceptance checks. |

## The five things that must be true at judging

1. Same task, same page: Shield OFF leaks, Shield ON blocks, task still completes.
2. Layer 1 catches at least one hiding trick that an existing open-source scanner misses,
   shown live (we already reproduced this gap, see doc 11).
3. The action guard blocks based on real-world rules, not only canaries.
4. Every number on a slide comes from `benchmark/results/`.
5. A cached replay and a backup video exist.
