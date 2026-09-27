"""agent.replay: plays saved runs with no network and no API key."""
import json
import time
from pathlib import Path

from agent.replay import replay

SAMPLE = Path(__file__).resolve().parent.parent / "contracts" / "sample_events.jsonl"


def test_replays_sample_events_in_order():
    expected = [json.loads(l) for l in SAMPLE.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert list(replay(SAMPLE, delay=0)) == expected


def test_delay_between_events(tmp_path):
    f = tmp_path / "r.jsonl"
    f.write_text('{"stage": "agent"}\n{"stage": "final"}\n', encoding="utf-8")
    t0 = time.monotonic()
    assert len(list(replay(f, delay=0.1))) == 2
    assert time.monotonic() - t0 >= 0.09  # one gap, none before the first event


def test_bad_input_never_raises(tmp_path):
    missing = list(replay(tmp_path / "nope.jsonl", delay=0))
    assert missing[0]["verdict"] == "FLAGGED"
    f = tmp_path / "bad.jsonl"
    f.write_text('{"stage": "agent"}\nnot json\n\n', encoding="utf-8")
    evts = list(replay(f, delay=0))
    assert [e["verdict"] if "verdict" in e else "ok" for e in evts] == ["ok", "FLAGGED"]
