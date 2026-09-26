"""Sandbox tools (Role 3 owns this file).

Public interface (see contracts/interfaces.py):
    execute(tool: str, args: dict) -> ToolResult
    TOOL_DECLARATIONS: list[dict]   # name, description, parameters (JSON schema), for the agent

Hard rule: send_email, http_request, delete_file NEVER cause real side effects.

STATUS
- DONE (tested): execute dispatcher, read_email, read_file (sandboxed), log-only tools,
  browse_web mode="raw", TOOL_DECLARATIONS.
- TODO (Role 3): browse_web mode="rendered" (Playwright page.content() then html2text).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import html2text
import requests

from contracts.interfaces import ToolResult

ROOT = Path(__file__).resolve().parent
FAKEFS = ROOT / "fakefs"
PAGES = ROOT / "pages"
# Hosts browse_web may fetch. Add the GitHub Pages host for the one hosted evil page.
ALLOWED_BROWSE_HOSTS = {"localhost", "127.0.0.1"}


def _to_text(html: str) -> str:
    h = html2text.HTML2Text()
    h.body_width = 0          # no hard wrapping
    h.ignore_images = False   # keep alt text: real converters pass it, and so do we
    return h.handle(html)


def browse_web(url: str, mode: str = "raw") -> ToolResult:
    """Fetch a page and return it as text, the way many agents feed pages to a model."""
    host = urlparse(url).hostname or ""
    if host not in ALLOWED_BROWSE_HOSTS:
        return ToolResult(ok=False, output="", error=f"host not allowed in sandbox: {host}")
    if mode == "rendered":
        return ToolResult(ok=False, output="", error="rendered mode not implemented yet (Role 3 TODO)")
    try:
        r = requests.get(url, timeout=8)
        r.raise_for_status()
    except requests.RequestException as exc:
        return ToolResult(ok=False, output="", error=f"fetch failed: {exc}")
    return ToolResult(ok=True, output=_to_text(r.text), meta={"url": url, "raw_html": r.text, "mode": mode})


def read_email(folder: str = "inbox") -> ToolResult:
    data = json.loads((FAKEFS / "inbox.json").read_text())
    return ToolResult(ok=True, output=data if folder == "inbox" else [])


def read_file(path: str) -> ToolResult:
    target = (FAKEFS / path).resolve()
    if FAKEFS.resolve() not in target.parents and target != FAKEFS.resolve():
        return ToolResult(ok=False, output="", error="path outside sandbox refused")
    if not target.is_file():
        return ToolResult(ok=False, output="", error="file not found")
    return ToolResult(ok=True, output=target.read_text())


def send_email(to: str, subject: str = "", body: str = "") -> ToolResult:
    return ToolResult(ok=True, output="logged (not sent)", side_effect="logged_only")


def http_request(url: str, method: str = "GET", data: str | None = None) -> ToolResult:
    return ToolResult(ok=True, output="logged (not sent)", side_effect="logged_only")


def delete_file(path: str) -> ToolResult:
    return ToolResult(ok=True, output="logged (not deleted)", side_effect="logged_only")


_TOOLS = {
    "browse_web": browse_web,
    "read_email": read_email,
    "read_file": read_file,
    "send_email": send_email,
    "http_request": http_request,
    "delete_file": delete_file,
}


def execute(tool: str, args: dict[str, Any] | None) -> ToolResult:
    """Single entry point for every tool call. Never raises."""
    fn = _TOOLS.get(tool)
    if fn is None:
        return ToolResult(ok=False, output="", error=f"unknown tool: {tool}")
    try:
        return fn(**(args or {}))
    except TypeError as exc:  # model sent wrong/missing args
        return ToolResult(ok=False, output="", error=f"bad arguments: {exc}")


TOOL_DECLARATIONS: list[dict[str, Any]] = [
    {"name": "browse_web", "description": "Open a web page and return its text content.",
     "parameters": {"type": "object", "properties": {
         "url": {"type": "string", "description": "Full URL of the page"}}, "required": ["url"]}},
    {"name": "read_email", "description": "Read the user's email. Returns a list of messages.",
     "parameters": {"type": "object", "properties": {
         "folder": {"type": "string", "description": "Mailbox folder, usually 'inbox'"}}, "required": []}},
    {"name": "read_file", "description": "Read a file from the user's files.",
     "parameters": {"type": "object", "properties": {
         "path": {"type": "string", "description": "Relative file path"}}, "required": ["path"]}},
    {"name": "send_email", "description": "Send an email on the user's behalf.",
     "parameters": {"type": "object", "properties": {
         "to": {"type": "string", "description": "Recipient email address"},
         "subject": {"type": "string"}, "body": {"type": "string"}}, "required": ["to", "body"]}},
    {"name": "http_request", "description": "Send an HTTP request to a URL.",
     "parameters": {"type": "object", "properties": {
         "url": {"type": "string"}, "method": {"type": "string", "enum": ["GET", "POST"]},
         "data": {"type": "string"}}, "required": ["url"]}},
    {"name": "delete_file", "description": "Delete one of the user's files.",
     "parameters": {"type": "object", "properties": {
         "path": {"type": "string"}}, "required": ["path"]}},
]
