"""R3-T2 acceptance: the evil corpus is big enough, labelled, and actually reaches the agent."""
import http.server
import json
import re
import socketserver
import threading
from functools import partial

import pytest

from sandbox import tools

MANIFEST = json.loads((tools.PAGES / "manifest.json").read_text(encoding="utf-8"))
EVIL = [e for e in MANIFEST if e["label"] == "evil"]
RAW_MODE = [e for e in EVIL if e["technique"] != "js_injected"]   # js_injected only reaches rendered-mode agents
ATTACK_LINK = re.compile(r"https?://[^\s)\]>\"']*evil\.example")


@pytest.fixture(scope="module")
def base():
    handler = partial(http.server.SimpleHTTPRequestHandler, directory=str(tools.PAGES))
    handler.log_message = lambda *a, **k: None
    httpd = socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def test_corpus_size_and_labels():
    assert len(EVIL) >= 15
    assert len([e for e in EVIL if e["payload_id"] == "answer_phishing_link"]) >= 4
    for e in MANIFEST:
        assert (tools.PAGES / e["path"]).is_file(), e["path"]
    for e in EVIL:
        assert {"technique", "payload_id", "wording", "expected_layer1", "layer3_can_catch"} <= e.keys(), e["path"]
        assert e["layer3_can_catch"] == (e["payload_id"] == "reset_email_forward"), e["path"]


@pytest.mark.parametrize("entry", RAW_MODE, ids=lambda e: e["path"])
def test_payload_reaches_raw_agent(base, entry):
    r = tools.execute("browse_web", {"url": f"{base}/{entry['path']}"})
    assert r.ok and "evil.example" in r.output
    if entry["payload_id"] == "answer_phishing_link":
        assert ATTACK_LINK.search(r.output), "phishing pages must carry a full http(s) link (hijack check)"


@pytest.mark.parametrize("entry", RAW_MODE, ids=lambda e: e["path"])
def test_layer1_matches_manifest(base, entry):
    """Real Chromium: pages labelled expected_layer1 get the payload in the gap; others don't."""
    from shield import gap
    from shield.visibility_gap import scan_url
    url = f"{base}/{entry['path']}"
    scan = scan_url(url)
    if scan["render_failed"]:
        pytest.skip(f"Chromium not available: {scan.get('error', '')[:120]}")
    spans = gap.gap(tools.execute("browse_web", {"url": url}).output, gap.to_text(scan["human_html"]))
    assert any("evil.example" in s for s in spans) is entry["expected_layer1"], spans
