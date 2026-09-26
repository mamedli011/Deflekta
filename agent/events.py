"""Event logging shared by agent and shield. Matches contracts/event.schema.json."""
from __future__ import annotations

import itertools
import json
from datetime import datetime, timezone
from pathlib import Path

RUNS = Path(__file__).resolve().parent.parent / "runs"
_counter = itertools.count(1)


def log_event(session_id: str, shield_on: bool, stage: str, verdict: str, reason: str, **fields) -> dict:
    RUNS.mkdir(exist_ok=True)
    evt = {
        "id": f"evt_{next(_counter):04d}",
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "session_id": session_id,
        "shield_on": shield_on,
        "stage": stage,
        "tool": fields.pop("tool", None),
        "args": fields.pop("args", {}),
        "verdict": verdict,
        "severity": fields.pop("severity", None),
        "layer": fields.pop("layer", None),
        "rule_triggered": fields.pop("rule_triggered", None),
        "reason": reason,
        "evidence": fields.pop("evidence", {}),
        "result": fields.pop("result", None),
        **fields,
    }
    with open(RUNS / f"{session_id}.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(evt) + "\n")
    return evt
