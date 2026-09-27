"""Cached demo mode (Role 2): yield events from runs/<file>.jsonl with a delay,
so the UI can play a saved run with no API calls.

CLI:  python -m agent.replay runs/demo_off.jsonl
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Iterator

from agent.events import RUNS


def _resolve(path: str | Path) -> Path:
    """Accept a full path, or a bare file name / session id inside runs/."""
    p = Path(path)
    if p.exists():
        return p
    name = p.name if p.suffix == ".jsonl" else f"{p.name}.jsonl"
    return RUNS / name


def replay(path: str | Path, delay: float = 0.8) -> Iterator[dict]:
    """Yield each event of a saved run, sleeping `delay` seconds between events.
    Never raises on a bad file: a missing file or unreadable line becomes an `agent` event
    with verdict FLAGGED, so the demo UI keeps running."""
    p = _resolve(path)
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        yield {"stage": "agent", "verdict": "FLAGGED", "reason": f"Replay file not readable: {p}",
               "result": repr(exc)}
        return
    first = True
    for n, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            evt = json.loads(line)
        except json.JSONDecodeError:
            evt = {"stage": "agent", "verdict": "FLAGGED", "reason": f"Bad JSON on line {n} of {p.name}"}
        if not first and delay > 0:
            time.sleep(delay)
        first = False
        yield evt


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--delay", type=float, default=0.8)
    a = ap.parse_args()
    for e in replay(a.path, a.delay):
        print(f"[{e.get('stage')}] {e.get('verdict')} {e.get('tool') or ''} {e.get('reason', '')}".rstrip())
