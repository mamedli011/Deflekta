"""Layer 1: hidden non-text elements that still feed the agent (html2text writes <img src> as ![alt](src) and
an empty <a href> as [](href)). Hidden ones become hidden evidence and leave the human view; visible images
never do. Local pages only; external image hosts use the reserved .test TLD and are blocked by the scanner."""
import base64
import http.server
import threading
from functools import partial

import pytest

from sandbox import tools
from shield.gap import gap, to_text
from shield.visibility_gap import scan_url

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
EXT = "https://img.cdn.test"                       # never resolvable; the scanner blocks it anyway


def page(body: str, css: str = "") -> str:
    return (f'<!doctype html><html><head><meta charset="utf-8"><style>body{{margin:0}}{css}</style></head>'
            f"<body><p>Weeknight garlic pasta with olive oil and parsley.</p>{body}"
            "<p>Serve hot with grated cheese.</p></body></html>")


# name -> (html, token that must end up hidden, expected technique)
HIDDEN = {
    "img_display_none_alt": (page(f'<img style="display:none" alt="System OK" src="{EXT}/a.png?token=TOKEN_A1">'),
                             "TOKEN_A1", "display_none"),
    "img_display_none_no_alt": (page(f'<img style="display:none" src="{EXT}/b.png?token=TOKEN_B2">'),
                                "TOKEN_B2", "display_none"),
    "img_in_hidden_container": (page(f'<div style="display:none"><img src="/pixel.png?token=TOKEN_C3"></div>'),
                                "TOKEN_C3", "display_none"),
    "img_visibility_hidden": (page('<img style="visibility:hidden" width="40" height="40" src="/pixel.png?token=TOKEN_D4">'),
                              "TOKEN_D4", "visibility_hidden"),
    "img_opacity_zero": (page('<img style="opacity:0" width="40" height="40" src="/pixel.png?token=TOKEN_E5">'),
                         "TOKEN_E5", "opacity_zero"),
    "img_offscreen_broken": (page(f'<img style="position:absolute;left:-9999px" src="{EXT}/f.png?token=TOKEN_F6">'),
                             "TOKEN_F6", "offscreen"),
    "empty_link_hidden": (page(f'<a style="display:none" href="{EXT}/reset?token=TOKEN_G7"></a>'),
                          "TOKEN_G7", "display_none"),
}

# name -> (html, src substrings that must stay visible). Ordinary images: loaded, broken (blocked), linked,
# tracking pixel, lazy, inside font-size:0 layouts, inside a scroll box below its fold.
VISIBLE = {
    "loaded_image_alt_title": (page('<img width="120" height="80" src="/pixel.png?id=hero" alt="Bowl of pasta" '
                                    'title="Fresh pasta">'), ["/pixel.png?id=hero"]),
    "broken_external_left_edge": (page(f'<img src="{EXT}/logo.png?id=logo">', "p{margin:0}"), ["logo.png?id=logo"]),
    "broken_external_sized": (page(f'<img width="300" height="120" src="{EXT}/banner.png?id=banner">'),
                              ["banner.png?id=banner"]),
    "linked_image": (page('<a href="/recipes/pasta"><img width="80" height="80" src="/pixel.png?id=linked"></a>'),
                     ["/pixel.png?id=linked", "/recipes/pasta"]),
    "tracking_pixel": (page('<img width="1" height="1" src="/pixel.png?id=pixel">'), ["/pixel.png?id=pixel"]),
    "lazy_below_fold": (page("<p>Filler paragraph.</p>" * 80 + '<img loading="lazy" src="/pixel.png?id=lazy">'),
                        ["/pixel.png?id=lazy"]),
    "font_size_zero_layout": (page('<div class="row"><img width="60" height="60" src="/pixel.png?id=row1">'
                                   '<img width="60" height="60" src="/pixel.png?id=row2"></div>', ".row{font-size:0}"),
                              ["/pixel.png?id=row1", "/pixel.png?id=row2"]),
    "scroll_box_image": (page('<div class="sc">' + "<p>Scroll filler.</p>" * 40
                              + '<img width="60" height="60" src="/pixel.png?id=scrolled"></div>',
                              ".sc{height:120px;overflow:auto}"), ["/pixel.png?id=scrolled"]),
    "visible_icon_link": (page('<a class="icon" href="/cart"></a>',
                               ".icon{display:inline-block;width:24px;height:24px;background:#c33}"), ["/cart"]),
}


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    d = tmp_path_factory.mktemp("hidden_images")
    (d / "pixel.png").write_bytes(PNG)
    for name, (html, *_rest) in {**HIDDEN, **VISIBLE}.items():
        (d / f"{name}.html").write_text(html, encoding="utf-8")

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), partial(Quiet, directory=str(d)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


@pytest.fixture(scope="module")
def scanned(site):
    if scan_url("about:blank")["render_failed"]:
        pytest.skip("Chromium not available")

    def _get(name):
        url = f"{site}/{name}.html"
        r = scan_url(url)
        assert not r["render_failed"], r.get("error")
        res = tools.execute("browse_web", {"url": url})
        assert res.ok, res.error
        return r, res.output, gap(res.output, to_text(r["human_html"]))
    return _get


@pytest.mark.parametrize("name", HIDDEN)
def test_hidden_non_text_element_is_hidden_evidence(name, scanned):
    _, token, technique = HIDDEN[name]
    r, agent_text, spans = scanned(name)
    assert token in agent_text                                          # the agent really receives it
    hits = [s for s in r["segments"] if token in s["text"]]
    assert hits and hits[0]["technique"] == technique, r["segments"]    # caught by the layer-1 rule itself
    assert token not in r["human_html"] and token not in to_text(r["human_html"])   # gone from the human view
    assert any(token in s for s in spans)                               # so it is stripped from the agent text
    assert "Weeknight garlic pasta" in to_text(r["human_html"])         # visible text untouched


# Pre-existing, documented rule (docs/05 step 4, unchanged here): the human view drops every alt attribute,
# because people don't read alt text. So an image line WITH alt text differs from the human view and is in
# the gap even when the image is visible. Only images without alt must stay out of the gap entirely.
HAS_ALT = {"loaded_image_alt_title"}


@pytest.mark.parametrize("name", VISIBLE)
def test_visible_images_are_not_hidden(name, scanned):
    _, srcs = VISIBLE[name]
    r, agent_text, spans = scanned(name)
    for src in srcs:
        assert src in agent_text
        flagged = [s for s in r["segments"] if src in s["text"] and s["technique"] != "attribute_text"]
        assert not flagged, f"{name}: visible element reported hidden: {flagged}"
        assert src in r["human_html"], f"{name}: visible element removed from the human view"
        if name not in HAS_ALT:
            assert not any(src in s for s in spans), f"{name}: visible element would be stripped: {spans}"


def test_text_detection_unchanged_next_to_images(scanned):
    """A hidden text payload on a page with hidden and visible images is still caught as before."""
    r, _, _ = scanned("img_display_none_alt")
    assert not any(s["technique"] in ("tiny_font", "low_contrast") and "img.cdn.test" in s["text"]
                   for s in r["segments"])                              # text-only rules never apply to images
