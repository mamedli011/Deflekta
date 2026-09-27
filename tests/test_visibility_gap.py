"""Layer 1 in real Chromium on every page in sandbox/pages/manifest.json (R4-T1).

The manifest (R3's corpus) is the source of truth for what layer 1 should do with each evil page:
- LAYER1  expected_layer1 true: the right hiding technique, no payload in the human view, and the
          exact agent-vs-human diff for a raw-mode agent.
- BYPASS  known_bypass true: a known layer-1 miss today. Asserted as a miss, so a fix shows up.
- LAYER2  expected_layer1 false, not a bypass (visible_disguised): the payload is visible on purpose;
          layer 1 must not call it hidden. Semantic detection belongs to layer 2 (the judge, R4-T4).
Benign pages: no serious findings. Skipped if Chromium isn't installed
(`python -m playwright install chromium`).
"""
import http.server
import json
import socketserver
import threading
from functools import partial

import pytest

from sandbox import tools
from shield.gap import _norm, gap, strip, to_text
from shield.pipeline import LOW_SEVERITY_MAX_CHARS

MANIFEST = json.loads((tools.PAGES / "manifest.json").read_text(encoding="utf-8"))
MARKERS = json.loads((tools.FAKEFS / "canaries.json").read_text(encoding="utf-8"))["attacker_markers"]
EVIL = [p for p in MANIFEST if p["label"] == "evil"]
BENIGN = [p for p in MANIFEST if p["label"] == "benign"]
LAYER1 = [p for p in EVIL if p.get("expected_layer1") is True]
BYPASS = [p for p in EVIL if p.get("known_bypass") is True]
LAYER2 = [p for p in EVIL if p.get("expected_layer1") is False and p.get("known_bypass") is not True]

# Manifest technique -> technique layer 1 must report for the payload element (R4's detector names).
EXPECTED_TECHNIQUE = {
    "inline_display_none": "display_none",
    "external_css_class": "display_none",
    "internal_css_class": "display_none",
    "js_injected": "offscreen",
    "offscreen": "offscreen",
    "inline_font_size_0": "tiny_font",
    "inline_white_on_white": "low_contrast",
    "inherited_low_contrast": "low_contrast",
    "inline_low_contrast_e5": "low_contrast",
    "img_alt": "attribute_text",
}
# Techniques whose payload a raw-mode agent never receives (only added by JavaScript).
NOT_IN_RAW_FETCH = {"js_injected"}
# R3's manifest contract: each evil page's tell-tale string is its "detect" field (default "evil.example",
# the generated recipe corpus). Pages where that string ALSO appears in visible text by design, with the
# number of visible occurrences (from R3's frozen pages). Layer 1 never removes visible text.
VISIBLE_PAYLOAD_OCCURRENCES = {"evil/resource_index.html": 1}   # visible "User Settings Endpoint" link


def _payload(page: dict) -> str:
    return page.get("detect", "evil.example")


def _has(text: str, page: dict) -> bool:
    return _payload(page) in text


def _has_marker(text: str) -> bool:
    return any(m in text.lower() for m in MARKERS)


def _ids(p: dict) -> str:
    return p["path"]


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
    assert EVIL and BENIGN and LAYER1


@pytest.mark.parametrize("page", EVIL, ids=_ids)
def test_manifest_groups_are_consistent(page):
    """Every evil page is in exactly one group, so none silently escapes the checks below."""
    assert isinstance(page.get("expected_layer1"), bool), "evil page needs expected_layer1: true/false"
    assert isinstance(page.get("known_bypass", False), bool), "known_bypass must be true/false if present"
    if page.get("known_bypass"):
        assert page["expected_layer1"] is False, "known_bypass: true requires expected_layer1: false"
    groups = [name for name, group in (("LAYER1", LAYER1), ("BYPASS", BYPASS), ("LAYER2", LAYER2))
              if page in group]
    assert len(groups) == 1, f"page is in groups {groups}, expected exactly one"


@pytest.mark.parametrize("page", LAYER1, ids=_ids)
def test_evil_payload_detected_with_expected_technique(page, scan):
    assert page["technique"] in EXPECTED_TECHNIQUE, \
        f"new technique {page['technique']!r}: add its expected layer-1 result to EXPECTED_TECHNIQUE"
    r = scan(page["path"])
    assert not r["render_failed"], r.get("error")
    hits = [s for s in r["segments"] if _has(s["text"], page)]
    assert hits, f"payload {_payload(page)!r} not reported; segments: {r['segments']}"
    assert {s["technique"] for s in hits} == {EXPECTED_TECHNIQUE[page["technique"]]}


@pytest.mark.parametrize("page", LAYER1 + BENIGN, ids=_ids)
def test_human_view_has_no_payload(page, scan):
    r = scan(page["path"])
    assert not r["render_failed"], r.get("error")
    assert r["human_html"]
    visible = VISIBLE_PAYLOAD_OCCURRENCES.get(page["path"], 0)
    assert to_text(r["human_html"]).count(_payload(page)) == visible
    if not visible:
        assert not _has(r["human_html"], page)


@pytest.mark.parametrize("page", LAYER1, ids=_ids)
def test_raw_agent_diff_is_exactly_the_payload(page, scan, browse):
    agent_text = browse(page["path"])
    spans = gap(agent_text, to_text(scan(page["path"])["human_html"]))
    if page["technique"] in NOT_IN_RAW_FETCH:
        # The raw agent never got the JS-added text, so there is nothing to strip.
        assert not _has(agent_text, page)
        assert spans == []
        return
    assert _has(agent_text, page)                         # the attack really reaches the agent
    payload_spans = [s for s in spans if _has(s, page)]
    assert payload_spans and all(len(s) > LOW_SEVERITY_MAX_CHARS for s in payload_spans), spans
    if "detect" not in page:
        assert len(spans) == 1, spans                     # generated corpus: one-sentence payload, no collateral
    else:
        # Hand-authored payloads can span sentences. No collateral: every removed sentence is hidden text
        # (inside a hidden segment) or an image line (alt text is hidden from people by definition, docs/05).
        hidden = [_norm(seg["text"]) for seg in scan(page["path"])["segments"]]
        for s in spans:
            assert any(_norm(s) in h for h in hidden) or s.lstrip().startswith("!["), f"visible text stripped: {s!r}"
    cleaned = strip(agent_text, spans)
    assert cleaned.count(_payload(page)) == VISIBLE_PAYLOAD_OCCURRENCES.get(page["path"], 0)
    assert "[hidden content removed by shield]" in cleaned


@pytest.mark.parametrize("page", BYPASS, ids=_ids)
def test_known_bypass_is_still_missed(page, scan, browse):
    """A documented layer-1 miss (known_bypass in R3's manifest). This asserts the miss so the
    benchmark reports it honestly. When a detector fix lands, this fails on purpose."""
    r = scan(page["path"])
    assert not r["render_failed"], r.get("error")
    assert _has(browse(page["path"]), page), "payload no longer reaches the agent; check the page"
    hits = [s for s in r["segments"] if _has(s["text"], page)]
    assert not hits, (
        f"{page['path']} ({page['technique']}) is now detected by layer 1 as "
        f"{sorted({s['technique'] for s in hits})}. Update R3's manifest: set known_bypass: false and "
        "expected_layer1: true for this page (sandbox/build_corpus.py), and add its technique to "
        "EXPECTED_TECHNIQUE.")
    assert _has(to_text(r["human_html"]), page), (
        f"{page['path']}: payload is no longer in the human view, so layer 1 now hides it. "
        "Update R3's manifest (known_bypass: false, expected_layer1: true).")


@pytest.mark.parametrize("page", LAYER2, ids=_ids)
def test_layer2_page_is_visible_to_layer1(page, scan, browse):
    """The payload is visible to people on purpose (e.g. visible_disguised). Layer 1 must not call it
    hidden or strip it; deciding whether it instructs the AI is layer 2's job (the judge, R4-T4)."""
    r = scan(page["path"])
    assert not r["render_failed"], r.get("error")
    agent_text = browse(page["path"])
    assert _has(agent_text, page), "payload no longer reaches the agent; check the page"
    human_text = to_text(r["human_html"])
    assert _has(human_text, page), "visible payload is missing from the human view (layer-1 false positive)"
    hits = [s for s in r["segments"] if _has(s["text"], page)]
    assert not hits, f"layer 1 reported visible text as hidden: {hits}"
    assert not any(_has(s, page) for s in gap(agent_text, human_text)), "visible payload would be stripped"


@pytest.mark.parametrize("page", BENIGN, ids=_ids)
def test_benign_page_has_no_serious_findings(page, scan, browse):
    r = scan(page["path"])
    assert not r["render_failed"], r.get("error")
    for s in r["segments"]:
        assert s["severity_hint"] == "low", s               # e.g. sr-only skip link
        assert not _has_marker(s["text"])
    spans = gap(browse(page["path"]), to_text(r["human_html"]))
    assert all(len(s) <= LOW_SEVERITY_MAX_CHARS for s in spans), spans   # FLAGGED at most, never STRIPPED
