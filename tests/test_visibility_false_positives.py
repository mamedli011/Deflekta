"""Layer 1 false-positive guards (R4-T5a): ordinary visible page content must not be treated as hidden.

A safety net before tightening the detector for the known bypasses (low alpha, opacity and font-size
thresholds, zero-size and clipped boxes, overlays, closed <details>). Each case is a small benign page in
real Chromium. "Visible" means: layer 1 reports no hidden segment containing the sentence, and the
agent-vs-human diff does not contain it (so check_input would never strip it).
Skipped if Chromium isn't installed (`python -m playwright install chromium`).
"""
import http.server
import socketserver
import threading
from functools import partial

import pytest

from sandbox import tools
from shield.gap import gap, to_text

HEAD = '<!doctype html><html><head><meta charset="utf-8"><style>body{margin:0;font:16px sans-serif;background:#fff;color:#222}{css}</style></head><body>'
TAIL = "<p>Serve the pasta hot with grated cheese on top.</p></body></html>"


def page(body: str, css: str = "") -> str:
    return HEAD.replace("{css}", css) + body + TAIL


# name -> (html, visible sentences that must survive layer 1)
CASES = {
    "plain_text": (page("<p>Boil the pasta in plenty of salted water.</p>"),
                   ["Boil the pasta in plenty of salted water."]),
    "small_10px_footer": (page('<footer class="f">Recipe text and photos copyright Nonna Kitchen.</footer>',
                               ".f{font-size:10px;color:#666}"),
                          ["Recipe text and photos copyright Nonna Kitchen."]),
    "light_grey_caption": (page('<p class="c">Photo taken on a sunny afternoon in Rome.</p>', ".c{color:#999}"),
                           ["Photo taken on a sunny afternoon in Rome."]),
    "translucent_0_6": (page('<p class="t">Tip: toast the breadcrumbs for extra crunch.</p>', ".t{opacity:.6}"),
                        ["Tip: toast the breadcrumbs for extra crunch."]),
    "nested_opacity_0_54": (page('<div class="o"><p class="t">Nested note about fresh basil leaves.</p></div>',
                                 ".o{opacity:.9}.t{opacity:.6}"),
                            ["Nested note about fresh basil leaves."]),
    "material_alpha_text": (page('<p class="m">Prep time is about twenty minutes in total.</p>',
                                 ".m{color:rgba(0,0,0,.87)}.m2{color:rgba(0,0,0,.54)}"
                                 ) .replace("</p>", '</p><p class="m2">Secondary text shows the cook time estimate.</p>', 1),
                            ["Prep time is about twenty minutes in total.",
                             "Secondary text shows the cook time estimate."]),
    "white_on_dark_banner": (page('<div class="b">Free shipping on all cookware this weekend.</div>',
                                  ".b{background:#1b1b1b;color:#fff;padding:12px}"),
                             ["Free shipping on all cookware this weekend."]),
    "css_fade_in_animation": (page('<p class="fade">Welcome back to the weekly recipe club.</p>',
                                   "@keyframes fi{from{opacity:0}to{opacity:1}}.fade{animation:fi .4s ease-in both}"),
                              ["Welcome back to the weekly recipe club."]),
    "js_fade_in_transition": (page('<p id="j" style="opacity:0;transition:opacity .3s">New recipes arrive every Friday morning.</p>'
                                   '<script>setTimeout(function(){document.getElementById("j").style.opacity=1},50)</script>'),
                              ["New recipes arrive every Friday morning."]),
    "sticky_header": (page('<header class="s">Nonna Kitchen main navigation bar</header>'
                           + "<p>Long article paragraph about sauces and ragu.</p>" * 30,
                           ".s{position:sticky;top:0;background:#fff}"),
                      ["Nonna Kitchen main navigation bar", "Long article paragraph about sauces and ragu."]),
    "fixed_header_and_cookie_bar": (page('<header class="fx">Fixed header with the site search box</header>'
                                         '<main style="padding-top:60px"><p>Main content starts below the header.</p></main>'
                                         '<div class="ck">We use cookies to remember your saved recipes.</div>',
                                         ".fx{position:fixed;top:0;left:0;right:0;height:50px;background:#fff}"
                                         ".ck{position:fixed;bottom:0;left:0;right:0;background:#eee}"),
                                    ["Fixed header with the site search box", "Main content starts below the header.",
                                     "We use cookies to remember your saved recipes."]),
    "scrollable_box_below_fold": (page('<div class="sc"><p>First line inside the scroll box.</p>'
                                       + "<p>Filler line in the scroll box.</p>" * 60
                                       + "<p>Last line you reach by scrolling the box.</p></div>",
                                       ".sc{height:120px;overflow:auto;border:1px solid #ccc}"),
                                  ["First line inside the scroll box.", "Last line you reach by scrolling the box."]),
    "scrollable_box_long_comment": (page('<div class="sc">'
                                         + "".join(f"<p>Comment number {i} about the recipe.</p>" for i in range(60))
                                         + "<p>Reader comment: we doubled the garlic and let the sauce simmer "
                                           "for an extra ten minutes.</p></div>",
                                         ".sc{height:120px;overflow:auto}"),
                                    ["Reader comment: we doubled the garlic and let the sauce simmer for an "
                                     "extra ten minutes."]),
    "overflow_scroll_below_fold": (page('<div class="sc">' + "<p>Scroll filler row.</p>" * 60
                                        + "<p>Bottom row of the always-scrollable box.</p></div>",
                                        ".sc{height:120px;overflow:scroll}"),
                                   ["Bottom row of the always-scrollable box."]),
    "nested_scroll_boxes": (page('<div class="outer">' + "<p>Outer filler row.</p>" * 40
                                 + '<div class="inner">' + "<p>Inner filler row.</p>" * 40
                                 + "<p>Deepest line inside the inner scroll box.</p></div></div>",
                                 ".outer{height:200px;overflow:auto}.inner{height:100px;overflow:auto}"),
                            ["Deepest line inside the inner scroll box."]),
    "horizontal_scroll_table": (page('<div class="hx"><table><tr>'
                                     + "<td>Column filler cell</td>" * 80
                                     + "<td>Rightmost cell reached by scrolling sideways.</td></tr></table></div>",
                                     ".hx{width:400px;overflow-x:auto}td{white-space:nowrap}"),
                                ["Rightmost cell reached by scrolling sideways."]),
    "long_page_below_viewport": (page("<p>Intro paragraph at the top of the page.</p>" + "<p>Middle filler text.</p>" * 120
                                      + "<p>Final paragraph far below the first screen.</p>"),
                                 ["Final paragraph far below the first screen."]),
    "ellipsis_truncated_title": (page('<h3 class="e">A very long recipe title that gets cut off with an ellipsis at the end</h3>',
                                      ".e{width:220px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}"),
                                 ["A very long recipe title that gets cut off with an ellipsis at the end"]),
    "mild_transforms": (page('<p class="r">Rotated sticker says chef recommended.</p>'
                             '<p class="k">Slightly shrunk badge for gluten free.</p>',
                             ".r{transform:rotate(-3deg)}.k{transform:scale(.9)}"),
                        ["Rotated sticker says chef recommended.", "Slightly shrunk badge for gluten free."]),
    "open_details": (page("<details open><summary>Nutrition facts per serving</summary>"
                          "<p>Each serving has about four hundred calories.</p></details>"),
                     ["Nutrition facts per serving", "Each serving has about four hundred calories."]),
    # Closed <details>: only the summary is asserted. Whether the collapsed body counts as "hidden" is an
    # open policy question (known_bypass closed_details vs normal FAQ accordions). No expectation imposed.
    "closed_details_summary_only": (page("<details><summary>Frequently asked question about storage</summary>"
                                         "<p>Leftovers keep in the fridge for three days.</p></details>"),
                                    ["Frequently asked question about storage"]),
}


# Known false positives in the CURRENT detector, recorded honestly instead of changing the expectation.
# strict=True: when the detector is fixed these XPASS and fail the suite, so the marker gets removed.
# (The scroll-container false positive was fixed in R4-T5b stage 1; its two entries were removed.)
KNOWN_FALSE_POSITIVES: dict[str, str] = {}

# Text a scroll container must NOT rescue: still offscreen after the stage-1 scroll fix.
# name -> (html, sentence that must be reported hidden as offscreen)
UNREACHABLE = {
    "scroll_box_negative_left": (page('<div class="sc"><p>Normal line in the box.</p>'
                                      '<p class="neg">Pushed far left inside the scroll box, unreachable.</p></div>',
                                      ".sc{position:relative;height:120px;overflow:auto}"
                                      ".neg{position:absolute;left:-9999px;top:10px}"),
                                 "Pushed far left inside the scroll box, unreachable."),
    "scroll_box_negative_top": (page('<div class="sc"><p class="up">Shifted above the scroll origin, unreachable.</p>'
                                     "<p>Normal line in the box.</p></div>",
                                     ".sc{height:120px;overflow:auto}.up{position:relative;top:-3000px}"),
                                "Shifted above the scroll origin, unreachable."),
    "fixed_far_below_inside_scroll_box": (page('<div class="sc"><p>Normal line in the box.</p>'
                                               '<p class="fx">Fixed far below the viewport, never scrolled in.</p></div>',
                                               ".sc{height:120px;overflow:auto}.fx{position:fixed;top:5000px}"),
                                          "Fixed far below the viewport, never scrolled in."),
    "scroll_box_itself_offscreen": (page('<div class="sc">' + "<p>Filler inside a hidden box.</p>" * 30
                                         + "<p>Content of a scroll box placed off the page.</p></div>",
                                         ".sc{position:absolute;left:-9999px;height:120px;overflow:auto}"),
                                    "Content of a scroll box placed off the page."),
    "clipped_inside_scroll_box": (page('<div class="sc"><div class="clip">' + "<p>Clip filler.</p>" * 40
                                       + "<p>Clipped by overflow hidden inside a scroll box.</p></div></div>",
                                       ".sc{height:120px;overflow:auto}.clip{height:0;overflow:hidden}"),
                                  "Clipped by overflow hidden inside a scroll box."),   # hidden/clip never rescues
}
CASE_PARAMS = [pytest.param(n, marks=pytest.mark.xfail(strict=True, reason=KNOWN_FALSE_POSITIVES[n]))
               if n in KNOWN_FALSE_POSITIVES else n for n in CASES]


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args) -> None:
        pass


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    d = tmp_path_factory.mktemp("benign_fp")
    for name, (html, _) in {**CASES, **UNREACHABLE}.items():
        (d / f"{name}.html").write_text(html, encoding="utf-8")
    handler = partial(_QuietHandler, directory=str(d))
    httpd = socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


@pytest.fixture(scope="module")
def scanned(site):
    from shield.visibility_gap import scan_url
    if scan_url("about:blank")["render_failed"]:
        pytest.skip("Chromium not available")
    cache = {}

    def _get(name):
        if name not in cache:
            url = f"{site}/{name}.html"
            r = scan_url(url)
            assert not r["render_failed"], r.get("error")
            res = tools.execute("browse_web", {"url": url})
            assert res.ok, res.error
            cache[name] = (r, gap(res.output, to_text(r["human_html"])))
        return cache[name]
    return _get


@pytest.mark.parametrize("name", CASE_PARAMS)
def test_visible_content_is_not_hidden(name, scanned):
    scan, spans = scanned(name)
    for sentence in CASES[name][1]:
        hidden = [s for s in scan["segments"] if sentence in s["text"]]
        assert not hidden, f"{name}: visible text reported hidden as {[s['technique'] for s in hidden]}"
        assert not any(sentence in s for s in spans), f"{name}: visible text would be stripped: {spans}"


def test_every_case_page_has_no_serious_gap(scanned):
    """Page-level view: nothing on these benign pages would be STRIPPED (gap sentences over 60 chars)."""
    from shield.pipeline import LOW_SEVERITY_MAX_CHARS
    serious = {n: [s for s in scanned(n)[1] if len(s) > LOW_SEVERITY_MAX_CHARS] for n in CASES
               if n != "closed_details_summary_only" and n not in KNOWN_FALSE_POSITIVES}
    assert not any(serious.values()), {n: s for n, s in serious.items() if s}


@pytest.mark.parametrize("name", UNREACHABLE)
def test_scroll_container_does_not_rescue_unreachable_text(name, scanned):
    """The scroll fix only rescues content a person can scroll to. These stay hidden as offscreen."""
    scan, spans = scanned(name)
    sentence = UNREACHABLE[name][1]
    hits = [s for s in scan["segments"] if sentence in s["text"]]
    assert hits and hits[0]["technique"] == "offscreen", f"{name}: expected offscreen, got {hits}"
    assert any(sentence in s for s in spans), f"{name}: unreachable text must be in the gap: {spans}"
