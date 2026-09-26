"""Layer 1 in real Chromium on every page in sandbox/pages/manifest.json (R4-T1).

Locks in: the right hiding technique per evil page, no payload in the human view,
the exact agent-vs-human diff for a raw-mode agent, and no serious findings on benign pages.
Skipped if Chromium isn't installed (`python -m playwright install chromium`).
"""
import http.server
import json
import socketserver
import threading
from functools import partial

import pytest

from sandbox import tools
from shield.gap import gap, strip, to_text
from shield.pipeline import LOW_SEVERITY_MAX_CHARS

MANIFEST = json.loads((tools.PAGES / "manifest.json").read_text(encoding="utf-8"))
MARKERS = json.loads((tools.FAKEFS / "canaries.json").read_text(encoding="utf-8"))["attacker_markers"]
EVIL = [p for p in MANIFEST if p["label"] == "evil"]
BENIGN = [p for p in MANIFEST if p["label"] == "benign"]

# Manifest technique -> technique layer 1 must report for the payload element.
EXPECTED_TECHNIQUE = {
    "inline_display_none": "display_none",
    "external_css_class": "display_none",
    "js_injected": "offscreen",
}
# Techniques whose payload a raw-mode agent never receives (only added by JavaScript).
NOT_IN_RAW_FETCH = {"js_injected"}


def _has_marker(text: str) -> bool:
    return any(m in text.lower() for m in MARKERS)


@pytest.fixture(scope="module")
def server():
    handler = partial(http.server.SimpleHTTPRequestHandler, directory=str(tools.PAGES))
    handler.log_message = lambda *a, **k: None
    httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


@pytest.fixture(scope="module")
def scan(server):
    """Render each page once per test run. Skips if Chromium can't start at all;
    a render failure on a real page after that is a test failure, not a skip."""
    from shield.visibility_gap import scan_url
    probe = scan_url("about:blank")
    if probe["render_failed"]:
        pytest.skip(f"Chromium not available: {probe.get('error', '')[:120]}")
    cache: dict[str, dict] = {}

    def _scan(path: str) -> dict:
        if path not in cache:
            cache[path] = scan_url(f"{server}/{path}")
        return cache[path]
    return _scan


@pytest.fixture(scope="module")
def browse(server):
    """What the raw-mode agent receives from browse_web."""
    def _browse(path: str) -> str:
        r = tools.execute("browse_web", {"url": f"{server}/{path}"})
        assert r.ok, r.error
        return r.output
    return _browse


def test_manifest_has_both_labels():
    assert EVIL and BENIGN


@pytest.mark.parametrize("page", EVIL, ids=lambda p: p["path"])
def test_evil_payload_detected_with_expected_technique(page, scan):
    assert page["technique"] in EXPECTED_TECHNIQUE, \
        f"new technique {page['technique']!r}: add its expected layer-1 result to EXPECTED_TECHNIQUE"
    r = scan(page["path"])
    assert not r["render_failed"], r.get("error")
    hits = [s for s in r["segments"] if _has_marker(s["text"])]
    assert hits, f"payload not reported; segments: {r['segments']}"
    assert {s["technique"] for s in hits} == {EXPECTED_TECHNIQUE[page["technique"]]}


@pytest.mark.parametrize("page", MANIFEST, ids=lambda p: p["path"])
def test_human_view_has_no_payload(page, scan):
    r = scan(page["path"])
    assert not r["render_failed"], r.get("error")
    assert r["human_html"]
    assert not _has_marker(r["human_html"])
    assert not _has_marker(to_text(r["human_html"]))


@pytest.mark.parametrize("page", EVIL, ids=lambda p: p["path"])
def test_raw_agent_diff_is_exactly_the_payload(page, scan, browse):
    agent_text = browse(page["path"])
    spans = gap(agent_text, to_text(scan(page["path"])["human_html"]))
    if page["technique"] in NOT_IN_RAW_FETCH:
        # The raw agent never got the JS-added text, so there is nothing to strip.
        assert not _has_marker(agent_text)
        assert spans == []
        return
    assert _has_marker(agent_text)                        # the attack really reaches the agent
    assert len(spans) == 1, spans                         # only the payload, no collateral
    assert _has_marker(spans[0]) and len(spans[0]) > LOW_SEVERITY_MAX_CHARS
    cleaned = strip(agent_text, spans)
    assert not _has_marker(cleaned)
    assert "[hidden content removed by shield]" in cleaned


@pytest.mark.parametrize("page", BENIGN, ids=lambda p: p["path"])
def test_benign_page_has_no_serious_findings(page, scan, browse):
    r = scan(page["path"])
    assert not r["render_failed"], r.get("error")
    for s in r["segments"]:
        assert s["severity_hint"] == "low", s               # e.g. sr-only skip link
        assert not _has_marker(s["text"])
    spans = gap(browse(page["path"]), to_text(r["human_html"]))
    assert all(len(s) <= LOW_SEVERITY_MAX_CHARS for s in spans), spans   # FLAGGED at most, never STRIPPED
