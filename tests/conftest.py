"""Shared pytest setup. Only loaded by pytest, never by the app.

One guard: the normal suite must never make a live Gemini judge call, even when a developer's .env
(loaded by agent/llm.py on import) provides GEMINI_API_KEY and JUDGE_MODEL. Every test starts with
shield.judge._generate replaced by a function that raises. check_input treats that as "judge
unavailable", exactly like the old stub. Tests that exercise the judge (tests/test_judge.py) script
_generate themselves with monkeypatch, which overrides this guard for that test only.
"""
import pytest

import shield.judge


def _live_judge_call_blocked(prompt: str) -> str:
    raise RuntimeError("pytest guard: live Gemini judge calls are disabled in tests. "
                       "Script shield.judge._generate with monkeypatch to test judge behavior.")


@pytest.fixture(autouse=True)
def _block_live_judge_calls(monkeypatch):
    monkeypatch.setattr(shield.judge, "_generate", _live_judge_call_blocked)
