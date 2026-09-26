# R1: Frontend + Pitch (owner: ______)

Folder: `frontend/`, plus slides, Devpost, demo video. Read first: `CLAUDE.md`,
`docs/13_interfaces.md`, `docs/04_data_contracts.md`, `docs/09_demo_and_pitch.md`, `docs/10_risks_and_judge_qa.md`.
You own what judges actually see. Build on `contracts/sample_events.jsonl` first; you don't need
anyone else's code to start.

## Tasks
- [ ] **R1-T1 Dashboard skeleton on sample data** (by CP1)
  - `pip install streamlit`. `streamlit run frontend/app.py`.
  - Layout: sidebar (Shield ON/OFF toggle, task text box, "Run agent" button, "Replay saved run" picker),
    main area: timeline of events, one row each: time, stage, tool, verdict badge, one-line reason.
  - Colors: ALLOWED green, FLAGGED and NEEDS_CONFIRM yellow, STRIPPED and BLOCKED red.
  - Clicking/expanding a row shows `args`, `evidence` (pretty JSON), `rule_triggered`, `layer`.
  - Done when: it renders all 5 sample events with the right colors.
- [ ] **R1-T2 Live + replay** (by CP2)
  - "Run agent" calls `agent.loop.run_agent(task, shield_on)` then renders `RunResult.events_path`.
  - "Replay" uses R2's `agent.replay.replay(path)` to animate `runs/demo_off.jsonl` / `demo_on.jsonl`.
  - Top banner per run from `RunResult.hijacked` and `hijack_kind`: "HIJACKED: your reset link was sent to
    the attacker" or "HIJACKED: the assistant told you to enter your password on a phishing site" (red), or
    "PROTECTED: attack stopped, task completed" (green).
  - Done when: both demo runs replay with no network.
- [ ] **R1-T3 Side-by-side view** (after CP2, high value)
  - For an `input` event: left, what a human sees (render the page in an iframe via
    `st.components.v1.iframe(url)` or a screenshot R4 can provide); right, the text the agent
    received with hidden segments highlighted in red (from `evidence.segments`).
- [ ] **R1-T4 Scorecard** (after R4-T5)
  - Render `benchmark/results/summary.md` in a tab. No hand-typed numbers anywhere.
- [ ] **R1-T5 Slides** (start early, finish by feature freeze)
  - 5 slides max, follow docs/09. Human story first. Baseline-gap table. Ablation ("why three layers").
    Numbers only from summary.md.
  - Never say "first", "only", or "all existing tools". One line disclosing the model config.
- [ ] **R1-T6 Backup video + Devpost** (at feature freeze)
  - Screen-record the full demo (replay mode is fine) under 2 minutes. Save it offline too.
  - Devpost: problem, solution, three layers, baseline-gap table, numbers with test-set labels,
    video, screenshots, repo link, sponsor challenges ticked, all teammates added.
- [ ] **R1-T7 Rehearse** 3 times with the team, with someone asking the doc-10 questions.

## Claude Code prompt for T1
"Read CLAUDE.md, docs/04, docs/13 and tasks/R1_frontend_pitch.md. Do R1-T1: build frontend/app.py in
Streamlit reading contracts/sample_events.jsonl. Keep it one file for now. Use st.expander per event
and colored badges. Don't import the agent yet. Run it and tell me how to open it."

## Watch out
- Streamlit reruns the whole script on every click. Keep run results in `st.session_state`.
- Secrets inside `evidence` are already masked, but `args` are logged as the model sent them. Don't display raw `args` of send_email in big text on
  slides if they contain the fake card; it's fake, but judges don't know that at a glance. Label it "fake bait data".
