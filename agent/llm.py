"""Gemini client wrapper (Role 2 owns this file).

STATUS: DRAFT, written from the google-genai docs but NOT RUN (no API key in the planning
environment). Role 2's first job is to run `python -m agent.llm` and fix anything that breaks.

Verified from docs (Sept 2026):
- Manual declarations: types.FunctionDeclaration(name=, description=, parameters_json_schema=)
- Disable auto-execution: types.AutomaticFunctionCallingConfig(disable=True)
- Calls come back in response.function_calls (each has .name, .args)
- Gemini 3: passing back thought signatures is mandatory for function calling. The SDK handles
  it IF you append response.candidates[0].content to history unchanged.
- Function responses carry the call id + name (required for Gemini 3.8 Flash on generateContent).
Check on the first real call: role used for function responses ("user" here).
"""
from __future__ import annotations

import os
import time

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()
_client: genai.Client | None = None


def client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return _client


def build_tools(declarations: list[dict]) -> list[types.Tool]:
    fns = [types.FunctionDeclaration(name=d["name"], description=d["description"],
                                     parameters_json_schema=d["parameters"]) for d in declarations]
    return [types.Tool(function_declarations=fns)]


def user_text(text: str) -> types.Content:
    return types.Content(role="user", parts=[types.Part.from_text(text=text)])


def function_responses(items: list[tuple[str | None, str, dict]]) -> types.Content:
    """items: [(call_id, tool_name, {"result": ...}), ...] in the same order as the calls.
    Gemini 3.8 Flash migration notes: every FunctionResponse must carry the call's id and name
    when using generateContent. Part.from_function_response() has no id argument (v2.25.0),
    so build the part explicitly."""
    parts = [types.Part(function_response=types.FunctionResponse(id=cid, name=n, response=r))
             for cid, n, r in items]
    return types.Content(role="user", parts=parts)


def generate(history: list[types.Content], tools: list[types.Tool], system: str,
             model: str | None = None, retries: int = 4):
    """One model turn. Retries 429 / RESOURCE_EXHAUSTED with 1, 2, 4, 8 s backoff."""
    model = model or os.environ["AGENT_MODEL"]
    cfg = types.GenerateContentConfig(
        system_instruction=system,
        tools=tools,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        # 3.8 Flash migration: don't set temperature/top_p/top_k; use thinking_level, not thinking_budget.
        thinking_config=types.ThinkingConfig(thinking_level=os.environ.get("THINKING_LEVEL", "low")),
    )
    # Optional, only for Flash-Lite agents (CP1 fallback step 3 in tasks/R2). Unset = model default.
    if os.environ.get("TEMPERATURE"):
        cfg.temperature = float(os.environ["TEMPERATURE"])
    for attempt in range(retries + 1):
        try:
            return client().models.generate_content(model=model, contents=history, config=cfg)
        except Exception as exc:  # narrow this once you see the SDK's error class
            if attempt < retries and ("429" in str(exc) or "RESOURCE_EXHAUSTED" in str(exc)):
                time.sleep(2 ** attempt)
                continue
            raise


if __name__ == "__main__":  # smoke test: one tool round trip
    from sandbox.tools import TOOL_DECLARATIONS
    hist = [user_text("Read my inbox and tell me the subject of the first email.")]
    r = generate(hist, build_tools(TOOL_DECLARATIONS), "You are a helpful assistant with tools.")
    print("function_calls:", [(c.name, dict(c.args or {})) for c in (r.function_calls or [])])
