# 08. Roles and Timeline

## Deadline and clock (Eastern Time)
**Submission deadline: Sunday, Sept 27, 2026, 11:00 AM ET.** Confirm with an organizer whether
11:00 AM is the Devpost cutoff or the end of hacking (Devpost can close earlier than hacking ends).
Our own target is to have Devpost fully submitted by **9:00 AM**, two hours early.

## Roles
Detailed, checkable tasks per role: `tasks/`. This table is the summary.


| Role | Owns | Must-have | Only after checkpoint 3 |
|------|------|-----------|-------------------------|
| R1 UI + Pitch | `frontend/`, slides, demo script | Shield toggle, Run button, live timeline (green/yellow/red), detail panel, scorecard, replay mode | "Human view vs AI view" side by side |
| R2 Agent | `agent/` | Loop with manual function calling, shield hooks, JSONL logging, replay | Second agent setup using `wrap_tools` |
| R3 Sandbox | `sandbox/` | Tools, fake FS + canaries, 3 evil pages then 15+, 30 benign pages, manifest | Host one evil page on GitHub Pages |
| R4 Shield | `shield/`, `benchmark/` | Run + fix layer 1, judge, pipeline, benchmark A/B/D | Benchmark C (outside datasets) |

## Checkpoints (assumes kickoff at 11:30 AM Saturday; shift everything if you start later)
| Clock (ET) | Checkpoint | Owner | If missed |
|------------|-----------|-------|-----------|
| Sat 11:30 AM | Kickoff meeting (doc 14). Keys created, `pytest -q` green on every laptop | all | - |
| Sat 12:15 PM | One real Gemini call works (`python -m agent.llm`) | R2 | Everyone helps R2 |
| Sat 2:30 PM | **CP1**: Shield OFF, agent hijacked on `recipe_external_css.html` | R2 + R3 | Nothing else matters until this works |
| Sat 5:00 PM | Layer 1 runs in a real browser on all evil pages | R4 | Cut the judge, keep layers 1 + 3 |
| Sat 9:00 PM | **CP2**: OFF then ON, both attack types, visible in the UI | all | Cut judge; cut corpus to 10 evil / 15 benign |
| Sat 10:30 PM | Sleep shift A starts (R1, R3) | R1, R3 | - |
| Sun 2:30 AM | **CP3**: benchmark A, B, E numbers in `summary.md`; shift A wakes, shift B (R2, R4) sleeps | all | Bonus list stays closed |
| Sun 6:30 AM | Shift B wakes | R2, R4 | - |
| Sun 7:00 AM | **Feature freeze.** Record backup video. Cached demo runs committed | all | - |
| Sun 9:00 AM | **Devpost submitted** (repo link, video, screenshots, tracks ticked) | R1 | Submit whatever works; edit later if allowed |
| Sun 9:00-10:30 AM | Rehearse pitch 3 times with doc-10 questions | all | - |
| Sun 11:00 AM | Hard deadline | - | - |

Why this sleep split: the person who owns the demo path (R2) and the pitch owner (R1) are never
asleep at the same time as the freeze, and R4 finishes benchmark numbers before sleeping.

## Cut list (first to go at the top)

1. Attacker-AI generator
2. Chrome extension
3. Second agent setup for `wrap_tools`
4. Benchmark C (outside datasets)
5. Side-by-side view (show hidden text in the detail panel instead)
6. Corpus size (go to 10 evil / 15 benign, keep numbers)

## Never cut
OFF vs ON demo, layer 1 with at least one baseline-gap technique, layer 3,
the dashboard, cached replay + backup video, the human-story pitch.
