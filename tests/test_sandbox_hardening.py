"""browse_web can't be steered out of the sandbox: redirects, off-allowlist subresources, huge pages."""
import http.server
import socketserver
import threading

import pytest

from sandbox import tools

SCRIPT_PAGE = ('<html><body><p>Recipe text that is long enough to read.</p>'
               '<script src="http://localhost:{port}/beacon.js"></script></body></html>')


class Handler(http.server.BaseHTTPRequestHandler):
    seen: list[str] = []

    def log_message(self, *a):
        pass

    def do_GET(self):
        Handler.seen.append(self.path)
        port = self.server.server_address[1]
        routes = {
            "/out": (302, {"Location": "http://evil.example/steal"}, b""),
            "/in": (302, {"Location": "/page"}, b""),
            "/loop": (302, {"Location": "/loop"}, b""),
            "/page": (200, {}, b"<html><body><p>Local page after a redirect.</p></body></html>"),
            "/huge": (200, {}, b"<html><body><p>" + b"a" * (tools.MAX_PAGE_BYTES + 500_000) + b"</p></body></html>"),
            "/script": (200, {}, SCRIPT_PAGE.format(port=port).encode()),
            "/beacon.js": (200, {"Content-Type": "text/javascript"}, b"document.title='beacon ran'"),
        }
        code, headers, body = routes.get(self.path, (404, {}, b""))
        self.send_response(code)
        for k, v in {"Content-Type": "text/html", **headers}.items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture(scope="module")
def base():
    httpd = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def test_redirect_out_of_sandbox_refused(base):
    r = tools.execute("browse_web", {"url": f"{base}/out"})
    assert not r.ok and "outside the sandbox" in r.error


def test_redirect_inside_sandbox_followed(base):
    r = tools.execute("browse_web", {"url": f"{base}/in"})
    assert r.ok and "Local page after a redirect" in r.output and r.meta["final_url"].endswith("/page")


def test_redirect_loop_stops(base):
    r = tools.execute("browse_web", {"url": f"{base}/loop"})
    assert not r.ok and "too many redirects" in r.error


def test_huge_page_truncated(base):
    r = tools.execute("browse_web", {"url": f"{base}/huge"})
    assert r.ok and r.meta["truncated"] and len(r.meta["raw_html"]) <= tools.MAX_PAGE_BYTES


def test_rendered_blocks_off_allowlist_requests(monkeypatch, base):
    # "localhost" points at the same test server but is taken off the allowlist for this test.
    monkeypatch.setattr(tools, "ALLOWED_BROWSE_HOSTS", {"127.0.0.1"})
    Handler.seen.clear()
    r = tools.execute("browse_web", {"url": f"{base}/script", "mode": "rendered"})
    if not r.ok and "Executable doesn't exist" in (r.error or ""):
        pytest.skip("Chromium not installed")
    assert r.ok and "/beacon.js" not in Handler.seen


def test_rendered_redirect_out_refused(base):
    r = tools.execute("browse_web", {"url": f"{base}/out", "mode": "rendered"})
    assert not r.ok


class Utf8NoCharset(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        body = '<html><head><meta charset="utf-8"></head><body><p>Heat to 220 °C · crème</p></body></html>'.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html")      # no charset in the header, like many servers
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def test_non_ascii_not_garbled_without_header_charset():
    httpd = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Utf8NoCharset)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        r = tools.execute("browse_web", {"url": f"http://127.0.0.1:{httpd.server_address[1]}/"})
    finally:
        httpd.shutdown()
    assert r.ok and "220 °C · crème" in r.output
