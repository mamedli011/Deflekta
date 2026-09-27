"""R3-T4: browse_web(mode="rendered") sees JS-injected text, and carries a same-load layer-1 scan."""
import http.server
import socketserver
import threading
from functools import partial

import pytest

from sandbox import tools

JS_PAGE = "evil/recipe_js_injected.html"


@pytest.fixture(scope="module")
def base():
    handler = partial(http.server.SimpleHTTPRequestHandler, directory=str(tools.PAGES))
    handler.log_message = lambda *a, **k: None
    httpd = socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def _rendered(url):
    r = tools.execute("browse_web", {"url": url, "mode": "rendered"})
    if not r.ok and "render failed" in (r.error or ""):
        pytest.skip(f"Chromium not available: {r.error[:120]}")
    return r


def test_rendered_sees_js_payload_raw_does_not(base):
    url = f"{base}/{JS_PAGE}"
    raw = tools.execute("browse_web", {"url": url})
    rendered = _rendered(url)
    assert raw.ok and "evil.example" not in raw.output
    assert rendered.ok and "evil.example" in rendered.output
    assert rendered.meta["mode"] == "rendered"


def test_rendered_scan_from_same_load(base):
    from shield import gap
    r = _rendered(f"{base}/{JS_PAGE}")
    scan = r.meta["scan"]
    assert not scan["render_failed"] and "evil.example" not in scan["human_html"]
    assert any("evil.example" in s["text"] for s in scan["segments"])
    spans = gap.gap(r.output, gap.to_text(scan["human_html"]))
    assert spans and all("evil.example" in s for s in spans)       # only the payload is in the gap


def test_rendered_output_has_no_scan_markers(base):
    r = _rendered(f"{base}/evil/recipe_external_css.html")
    assert "data-iis-hidden" not in r.meta["raw_html"]              # agent's view taken before the scan


def test_browse_mode_env_default(monkeypatch, base):
    calls = []
    monkeypatch.setitem(tools._TOOLS, "browse_web", lambda url, mode="raw": calls.append(mode) or
                        tools.ToolResult(ok=True, output=""))
    monkeypatch.setenv("BROWSE_MODE", "rendered")
    tools.execute("browse_web", {"url": f"{base}/x"})
    monkeypatch.delenv("BROWSE_MODE")
    tools.execute("browse_web", {"url": f"{base}/x"})
    assert calls == ["rendered", "raw"]


def test_rendered_bad_host_refused():
    r = tools.execute("browse_web", {"url": "http://example.com/", "mode": "rendered"})
    assert not r.ok and "not allowed" in r.error
