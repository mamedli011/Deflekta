# agent/ (Role 2)
Task list: `tasks/R2_agent.md`. Interface: `run_agent(task, shield_on, session_id=None) -> RunResult`.
- Model calls only through `agent/llm.py`. Automatic function calling stays disabled.
- Append `resp.candidates[0].content` to history unchanged.
- Every tool call goes: `check_action` (if shield on) -> `execute` (only if ALLOWED) -> `check_input` (browse_web, shield on).
- Every decision is logged with `log_event`. The `final` event is always written, even on errors.
- `tests/test_agent_loop_offline.py` must stay green. If you change the loop, update that test.
- Don't add instructions to the system prompt that make the agent more or less gullible without telling the team.
