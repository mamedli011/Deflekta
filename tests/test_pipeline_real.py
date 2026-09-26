"""R4-T2 Stage A: the real check_input path, offline (no API key, no quota).

Real browse_web text + real check_input + real Chromium layer-1 scan. Nothing is faked.
The judge (layer 2, R4-T4) is switched off with SHIELD_LAYERS=1,3 so these results don't
depend on it. Skipped if Chromium isn't installed (`python -m playwright install chromium`).
"""
import http.server
import json
import socketserver
import threading
from functools import partial

import pytest

from sandbox import tools
from shield import pipeline

MANIFEST = json.loads((tools.PAGES / "manifest.json").read_text(encoding="utf-8"))
MARKERS = json.loads((tools.FAKEFS / "canaries.json").read_text(encoding="utf-8"))["attacker_markers"]
PLACEHOLDER = "[hidden content removed by shield]"
# Payload is only added by JavaScript, so a raw-mode agent never receives it.
NOT_IN_RAW_FETCH = {"js_injected"}

EVIL = [p for p in MANIFEST if p["label"] == "evil" and p.get("expected_layer1")]
EVIL_RAW = [p for p in EVIL if p["technique"] not in NOT_IN_RAW_FETCH]
EVIL_JS = [p for p in EVIL if p["technique"] in NOT_IN_RAW_FETCH]
BENIGN = [p for p in MANIFEST if p["label"] == "benign"]


def _has_marker(text: str) -> bool:
    return any(m in text.lower() for m in MARKERS)


def _ids(p: dict) -> str:
    return p["path"]


@pytest.fixture(scope="module")
def server():
    """Serve sandbox/pages. Skips the module if Chromium can't start at all."""
    from shield.visibility_gap import scan_url
    probe = scan_url("about:blank")
    if probe["render_failed"]:
        pytest.skip(f"Chromium not available: {probe.get('error', '')[:120]}")
    handler = partial(http.server.SimpleHTTPRequestHandler, directory=str(tools.PAGES))
    handler.log_message = lambda *a, **k: None
    httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


@pytest.fixture
def run(server, monkeypatch):
    """browse_web (raw mode) the page, then run the real check_input on exactly that text,
    the same way agent/loop.py does. Returns (agent_text, decision)."""
    def _run(path: str, layers: str):
        monkeypatch.setenv("SHIELD_LAYERS", layers)
        monkeypatch.setenv("BROWSE_MODE", "raw")
        url = f"{server}/{path}"
        res = tools.execute("browse_web", {"url": url})
        assert res.ok, res.error
        return res.output, pipeline.check_input(url, res.output, res.meta.get("raw_html"))
    return _run


@pytest.mark.parametrize("page", EVIL_RAW, ids=_ids)
def test_hidden_payload_is_stripped(page, run):
    agent_text, d = run(page["path"], "1,3")
    assert _has_marker(agent_text)                               # the attack really reached the agent
    assert not d.render_failed
    assert d.verdict == "STRIPPED" and d.severity == "high" and d.layer == 1
    assert d.rule_triggered == "hidden_from_human_fed_to_ai"
    assert not _has_marker(d.clean_text)                         # payload gone
    assert d.clean_text.count(PLACEHOLDER) == 1                  # exactly one sentence removed
    # Everything else the agent was given is untouched (the task can still be done).
    assert d.clean_text.replace(PLACEHOLDER, "") == agent_text.replace(d.segments[0]["text"], "")
    # Evidence shape R1 relies on: the gap sentence comes first.
    assert _has_marker(d.segments[0]["text"])


@pytest.mark.parametrize("page", EVIL_JS, ids=_ids)
def test_js_payload_not_fed_to_raw_agent_is_allowed(page, run):
    agent_text, d = run(page["path"], "1,3")
    assert not _has_marker(agent_text)
    assert not d.render_failed
    assert d.verdict == "ALLOWED" and d.clean_text == agent_text


@pytest.mark.parametrize("page", BENIGN, ids=_ids)
def test_benign_page_never_stripped(page, run):
    agent_text, d = run(page["path"], "1,3")
    assert not d.render_failed
    assert d.verdict in ("ALLOWED", "FLAGGED"), (d.verdict, d.segments)
    if d.verdict == "FLAGGED":
        assert d.severity == "low"
        assert all(len(s["text"]) <= pipeline.LOW_SEVERITY_MAX_CHARS
                   for s in d.segments if set(s) == {"text"})  # gap sentences only
    assert not _has_marker(d.clean_text)


@pytest.mark.parametrize("page", EVIL_RAW, ids=_ids)
def test_ablation_layer3_only_lets_payload_through(page, run, monkeypatch):
    calls = []
    real_scan = pipeline._scan
    monkeypatch.setattr(pipeline, "_scan", lambda url: calls.append(url) or real_scan(url))
    agent_text, d = run(page["path"], "3")
    assert calls == []                                           # layer 1 never ran
    assert d.verdict == "ALLOWED" and d.layer is None
    assert d.clean_text == agent_text and _has_marker(d.clean_text)   # payload reaches the agent
