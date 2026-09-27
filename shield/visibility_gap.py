"""Layer 1: visibility-gap detector.

STATUS: written without a browser available. Not yet executed (JS syntax-checked).
The comparison logic that uses its output (shield/gap.py) IS tested. First task for Role 4:
run it on sandbox/pages (served on :8000) and fix what breaks. See docs/05.

Idea: render the page in Chromium, read *computed* styles for every element with direct
text, mark the ones a human can't see, and return a "human view" HTML with those elements and
all alt/aria-label/title attributes removed. shield/gap.py then diffs the agent's text against
html2text(human view). The segments list is kept for evidence and severity.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass

from bs4 import BeautifulSoup, Comment

WALK_JS = r"""
() => {
  const out = [];
  const docW = Math.max(document.documentElement.scrollWidth, window.innerWidth);
  const docH = Math.max(document.documentElement.scrollHeight, window.innerHeight);

  function parseRGB(s) {
    const m = s && s.match(/rgba?\(([^)]+)\)/);
    if (!m) return null;
    const p = m[1].split(',').map(x => parseFloat(x));
    return {r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1};
  }
  function lum(c) {
    const f = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b);
  }
  function contrast(a, b) {
    const l1 = lum(a), l2 = lum(b);
    return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
  }
  // Effective background color, or null if an image/gradient sits behind the text first.
  // We can't know the color of an image, so no contrast verdict (white text on a hero banner is visible).
  function effectiveBg(el) {
    for (let e = el; e; e = e.parentElement) {
      const cs = getComputedStyle(e);
      const c = parseRGB(cs.backgroundColor);
      if (c && c.a > 0.5) return c;
      if (cs.backgroundImage && cs.backgroundImage !== 'none') return null;
    }
    return {r: 255, g: 255, b: 255, a: 1};
  }
  function cssPath(el) {
    const parts = [];
    for (let e = el; e && e.nodeType === 1 && parts.length < 4; e = e.parentElement) {
      let s = e.tagName.toLowerCase();
      if (e.id) { s += '#' + e.id; parts.unshift(s); break; }
      if (e.classList.length) s += '.' + [...e.classList].slice(0, 2).join('.');
      parts.unshift(s);
    }
    return parts.join(' > ');
  }
  // Does scrolling container c move el? Not if el (or an ancestor below c) is position:fixed, or is
  // absolutely positioned with its containing block outside c. Transforms are ignored (conservative:
  // answering "no" keeps the plain document check).
  function scrolledBy(el, c) {
    let needPositioned = false;
    for (let n = el; n && n !== c; n = n.parentElement) {
      const p = getComputedStyle(n).position;
      if (p === 'fixed') return false;
      if (needPositioned && p !== 'static') needPositioned = false;
      if (p === 'absolute') needPositioned = true;
    }
    return !(needPositioned && getComputedStyle(c).position === 'static');
  }
  // Outside the document on either axis. Inside an overflow:auto/scroll container, content at a
  // positive offset is reachable by scrolling that container, so it only counts as offscreen if it
  // sits before the container's scroll origin (e.g. left:-9999px), lies outside it on an axis the
  // container can't scroll, or the container itself is offscreen. overflow:hidden/clip never rescues.
  function isOffscreen(el, r) {
    const x = r.left + window.scrollX, y = r.top + window.scrollY;
    const outX = x + r.width <= 0 || x >= docW, outY = y + r.height <= 0 || y >= docH;
    if (!outX && !outY) return false;
    for (let c = el.parentElement; c && c !== document.body && c !== document.documentElement; c = c.parentElement) {
      const ccs = getComputedStyle(c);
      const sx = /auto|scroll/.test(ccs.overflowX), sy = /auto|scroll/.test(ccs.overflowY);
      if (!sx && !sy) {
        if (/hidden|clip/.test(ccs.overflowX + ccs.overflowY)) return true;   // clipped on the way: no rescue
        continue;
      }
      if (!scrolledBy(el, c)) return true;
      if ((outX && !sx) || (outY && !sy)) return true;
      const cr = c.getBoundingClientRect();
      const relX = r.left - cr.left - c.clientLeft + c.scrollLeft;
      const relY = r.top - cr.top - c.clientTop + c.scrollTop;
      if (relX + r.width <= 0 || relY + r.height <= 0) return true;              // before the scroll origin
      if (relX >= c.scrollWidth || relY >= c.scrollHeight) return true;         // beyond the scroll range
      return isOffscreen(c, cr);
    }
    return true;
  }

  const all = document.body ? document.body.querySelectorAll('*') : [];
  for (const el of all) {
    if (['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE', 'SVG'].includes(el.tagName.toUpperCase())) continue;
    let text = '';
    for (const n of el.childNodes) if (n.nodeType === 3) text += n.textContent;
    text = text.replace(/\s+/g, ' ').trim();
    if (text.length < 3) continue;

    const reasons = [];
    let opacity = 1;
    for (let e = el; e; e = e.parentElement) {
      const cs = getComputedStyle(e);
      if (cs.display === 'none') { reasons.push('display_none'); break; }
      opacity *= parseFloat(cs.opacity || '1');
    }
    const cs = getComputedStyle(el);
    if (cs.visibility === 'hidden' || cs.visibility === 'collapse') reasons.push('visibility_hidden');
    if (opacity < 0.05) reasons.push('opacity_zero');
    if (parseFloat(cs.fontSize) < 2) reasons.push('tiny_font');

    if (!reasons.includes('display_none')) {
      const r = el.getBoundingClientRect();
      if (isOffscreen(el, r)) reasons.push('offscreen');
      if ((r.width < 2 || r.height < 2) && cs.overflow === 'hidden') reasons.push('clipped');
      if (cs.clipPath && cs.clipPath !== 'none' && /inset\(\s*(50%|100%)/.test(cs.clipPath)) reasons.push('clipped');
      if (cs.clip && /rect\(\s*0(px)?[ ,]+0(px)?[ ,]+0(px)?[ ,]+0(px)?\s*\)/.test(cs.clip)) reasons.push('clipped');
      const fg = parseRGB(cs.color), bg = effectiveBg(el);
      if (fg && bg && contrast(fg, bg) < 1.5) reasons.push('low_contrast');
    }
    if (reasons.length) {
      el.setAttribute('data-iis-hidden', reasons[0]);
      out.push({text: text.slice(0, 2000), technique: reasons[0], all_techniques: reasons,
                selector: cssPath(el),
                sr_only: /sr-only|visually-hidden|screen-reader/i.test(el.className || '')});
    }
  }
  for (const el of document.querySelectorAll('[alt],[aria-label],[title]')) {
    for (const a of ['alt', 'aria-label', 'title']) {
      const v = (el.getAttribute(a) || '').trim();
      if (v.length >= 20) out.push({text: v.slice(0, 2000), technique: 'attribute_text',
                                   all_techniques: ['attr:' + a], selector: cssPath(el), sr_only: false});
    }
  }
  return out;
}
"""

# Human view: the rendered DOM minus everything a person can't see or never reads.
HUMAN_HTML_JS = r"""
() => {
  const root = document.documentElement.cloneNode(true);
  root.querySelectorAll('[data-iis-hidden], script, style, noscript, template').forEach(e => e.remove());
  root.querySelectorAll('[alt],[aria-label],[title]').forEach(e => {
    e.removeAttribute('alt'); e.removeAttribute('aria-label'); e.removeAttribute('title');
  });
  return root.outerHTML;
}
"""


@dataclass
class HiddenSegment:
    text: str
    technique: str
    selector: str
    severity_hint: str
    all_techniques: list[str]


def _severity(seg: dict) -> str:
    if seg["technique"] == "attribute_text":
        return "low"
    if seg.get("sr_only") and len(seg["text"]) < 60:
        return "low"
    return "medium"


def html_comments(html: str) -> list[HiddenSegment]:
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for c in soup.find_all(string=lambda s: isinstance(s, Comment)):
        t = " ".join(str(c).split())
        if len(t) >= 20:
            out.append(HiddenSegment(t[:2000], "html_comment", "<!-- -->", "low", ["html_comment"]))
    return out


def noscript_text(html: str) -> list[str]:
    """Text inside <noscript>. A raw-HTML agent receives it, a JS-enabled browser never draws it,
    so it always shows up in the gap. pipeline.py lowers its severity (still stripped)."""
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for ns in soup.find_all("noscript"):
        # With scripting on, the browser keeps <noscript> contents as raw text; parse it again.
        t = " ".join(BeautifulSoup(ns.decode_contents(), "html.parser").get_text(" ").split())
        if t:
            out.append(t[:2000])
    return out


def scan_page(page, url: str) -> dict:
    """Layer-1 scan of an already-loaded Playwright page. Used by scan_url and by
    sandbox browse_web(mode="rendered"), so the agent's text and the scan come from ONE page load
    (a cloaking server can't show the scanner one page and the agent another).
    Call it AFTER reading page.content() for the agent: it marks hidden elements in the DOM."""
    raw = page.evaluate(WALK_JS)          # also marks hidden elements
    human_html = page.evaluate(HUMAN_HTML_JS)
    return _result(url, raw, human_html, page.content())


def scan_url(url: str, timeout_ms: int = 10_000) -> dict:
    """Render `url` and return hidden segments. Never raises: returns render_failed=True instead."""
    try:
        from playwright.sync_api import sync_playwright  # lazy, so tests don't need it
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                page = browser.new_page()
                page.goto(url, wait_until="networkidle", timeout=timeout_ms)
                return scan_page(page, url)
            finally:
                browser.close()
    except Exception as exc:  # timeouts, DNS, crashes: never crash the demo
        return {"url": url, "render_failed": True, "error": repr(exc), "segments": [],
                "human_html": None, "noscript_text": []}


def _result(url: str, raw: list[dict], human_html: str, html: str) -> dict:
    result: dict = {"url": url, "render_failed": False}
    segs = [HiddenSegment(r["text"], r["technique"], r["selector"], _severity(r), r["all_techniques"])
            for r in raw]
    segs += html_comments(html)
    result["segments"] = [asdict(s) for s in segs]
    result["noscript_text"] = noscript_text(html)
    result["human_html"] = human_html
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    print(json.dumps(scan_url(ap.parse_args().url), indent=2))
