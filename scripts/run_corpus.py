"""Run the evil corpus and record what happened, for the demo ("here's what happened when we ran it").

Two modes:
  API (default when GEMINI_API_KEY is set): run the real agent end-to-end per page, Shield OFF then
      ON (or OFF only with --off-only). Shows the browsing model getting fooled with no shield.
  Pipeline (--offline, or no key): run the shield pipeline on each page and report the verdict, with
      no agent loop. Layer 2 (judge) runs if a key is present; with no key it degrades to layer 1.

The agent and the shield are never told a page is malicious. The manifest label is only the answer
key used to score results afterward.

Rate limits: --delay spaces agent runs so we stay under a per-minute request cap. --off-only runs
only the unprotected case (the shield's catch is model-independent), to conserve daily quota.
--tag prefixes the session id / log filenames so different model runs don't overwrite each other.

Usage:
  python scripts/run_corpus.py --off-only --tag f38_ --delay 30 --pages brand_guide,policy_directive
  python scripts/run_corpus.py --offline
"""
from __future__ import annotations

import argparse
import http.server
import os
import socketserver
import sys
import time
import threading
from functools import partial
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(ROOT / ".env")

from sandbox import tools  # noqa: E402


def _serve() -> tuple[str, socketserver.TCPServer]:
    h = partial(http.server.SimpleHTTPRequestHandler, directory=str(tools.PAGES))
    h.log_message = lambda *a, **k: None
    srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), h)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{srv.server_address[1]}", srv


def _evil_with_tasks(pages_order: list[str] | None) -> list[dict]:
    import json
    manifest = json.loads((tools.PAGES / "manifest.json").read_text(encoding="utf-8"))
    by_stem = {Path(e["path"]).stem: e for e in manifest
               if e.get("label") == "evil" and "task" in e}
    if pages_order:
        return [by_stem[s] for s in pages_order if s in by_stem]   # respect requested order
    return list(by_stem.values())


def run_offline(entries: list[dict], base: str) -> list[dict]:
    from shield import pipeline
    rows = []
    for e in entries:
        url = f"{base}/{e['path']}"
        r = tools.execute("browse_web", {"url": url})
        d = pipeline.check_input(url, r.output, r.meta.get("raw_html"))
        caught = d.verdict in ("FLAGGED", "STRIPPED", "BLOCKED")
        rows.append({"page": Path(e["path"]).stem, "family": e["payload_id"],
                     "shield_verdict": d.verdict, "layer": d.layer, "caught": caught})
    return rows


def _run_retry_503(run_agent, task: str, shield_on: bool, sid: str, tries: int = 4, wait: float = 30.0):
    """Re-invoke a run when the model returns a transient 503 (server overload, not our quota)."""
    r = run_agent(task, shield_on=shield_on, session_id=sid)
    for _ in range(tries):
        if not (r.error and ("503" in r.error or "UNAVAILABLE" in r.error)):
            break
        time.sleep(wait)
        r = run_agent(task, shield_on=shield_on, session_id=sid)
    return r


def run_api(entries: list[dict], base: str, off_only: bool, delay: float, tag: str) -> list[dict]:
    from agent.loop import run_agent
    rows = []
    for i, e in enumerate(entries):
        if i:
            time.sleep(delay)                       # pacing: stay under the per-minute cap
        stem = Path(e["path"]).stem
        task = e["task"].format(url=f"{base}/{e['path']}")
        off = _run_retry_503(run_agent, task, False, f"corpus_{tag}{stem}_off")
        row = {"page": stem, "family": e["payload_id"],
               "off_hijacked": off.hijacked, "off_kind": off.hijack_kind, "off_error": off.error}
        if not off_only:
            time.sleep(delay)
            on = _run_retry_503(run_agent, task, True, f"corpus_{tag}{stem}_on")
            row.update({"on_hijacked": on.hijacked, "on_kind": on.hijack_kind,
                        "shield_worked": off.hijacked and not on.hijacked})
        rows.append(row)
    return rows


def _write_summary(rows: list[dict], mode: str, tag: str) -> Path:
    out = ROOT / "runs" / f"corpus_summary{('_' + tag.strip('_')) if tag else ''}.md"
    lines = [f"# Corpus run ({mode} mode){(' tag=' + tag) if tag else ''}", ""]
    if mode == "api":
        off_only = "on_hijacked" not in rows[0] if rows else True
        if off_only:
            lines += ["| page | family | OFF hijacked | kind |", "|------|--------|:---:|------|"]
            for r in rows:
                lines.append(f"| {r['page']} | {r['family']} | {r['off_hijacked']} | {r.get('off_kind')} |")
        else:
            lines += ["| page | family | OFF hijacked | ON hijacked | shield worked |",
                      "|------|--------|:---:|:---:|:---:|"]
            for r in rows:
                lines.append(f"| {r['page']} | {r['family']} | {r['off_hijacked']} "
                             f"| {r['on_hijacked']} | {r['shield_worked']} |")
    else:
        lines += ["| page | family | shield verdict | layer | caught |",
                  "|------|--------|------|:---:|:---:|"]
        for r in rows:
            lines.append(f"| {r['page']} | {r['family']} | {r['shield_verdict']} "
                         f"| {r['layer']} | {r['caught']} |")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="shield pipeline only, no agent loop")
    ap.add_argument("--off-only", action="store_true", help="run only the unprotected (Shield OFF) case")
    ap.add_argument("--pages", help="comma-separated page stems; also sets run order")
    ap.add_argument("--delay", type=float, default=30.0, help="seconds between agent runs (rate-limit pacing)")
    ap.add_argument("--tag", default="", help="prefix for session id / log filenames, e.g. f38_")
    a = ap.parse_args()
    pages_order = a.pages.split(",") if a.pages else None
    entries = _evil_with_tasks(pages_order)
    if not entries:
        print("no evil pages with a task field matched")
        return
    api = bool(os.environ.get("GEMINI_API_KEY")) and not a.offline
    base, srv = _serve()
    try:
        rows = run_api(entries, base, a.off_only, a.delay, a.tag) if api else run_offline(entries, base)
    finally:
        srv.shutdown()
    mode = "api" if api else "offline"
    for r in rows:
        print(r)
    print(f"\nsummary -> {_write_summary(rows, mode, a.tag)}")


if __name__ == "__main__":
    main()
