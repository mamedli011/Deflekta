"""Fetch real benign pages as frozen offline snapshots (R3-T3, false-positive corpus).

Run: python -m sandbox.fetch_benign

For each site it loads the page in headless Chromium, waits for load + ~2s, inlines every
stylesheet the page actually used (captured from network responses) into a <style> block,
removes every <script> so the copy is a frozen snapshot of what a person saw, and writes it to
sandbox/pages/benign/{slug}/index.html. Image src is left as-is (images fail offline; alt text
is kept on purpose). Scripts are stripped, so the offline copy renders fully from disk with no
network -- which is required because layer 1 aborts every off-sandbox request.

It then merges one manifest entry per saved page into pages/manifest.json (benign entries only,
evil and the hand-made benign page are left untouched) and rewrites benign/ATTRIBUTION.md.

Nothing here runs inside the agent. This is a build-time tool.
"""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

PAGES = Path(__file__).resolve().parent / "pages"
BENIGN = PAGES / "benign"
MANIFEST = PAGES / "manifest.json"
ATTRIBUTION = BENIGN / "ATTRIBUTION.md"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

# slug, url, source, license, redistributable
# Redistributable pages are safe to commit (open licence or US-government work).
# Local-only pages are gitignored: kept on disk for false-positive testing, never committed.
SITES: list[dict] = [
    # ---- redistributable (committed) ----
    {"slug": "wikipedia_pasta", "url": "https://en.wikipedia.org/wiki/Pasta",
     "source": "Wikipedia: Pasta", "license": "CC BY-SA 4.0", "redistributable": True},
    {"slug": "wikipedia_css", "url": "https://en.wikipedia.org/wiki/Cascading_Style_Sheets",
     "source": "Wikipedia: Cascading Style Sheets", "license": "CC BY-SA 4.0", "redistributable": True},
    {"slug": "wikipedia_chocolate_chip_cookie", "url": "https://en.wikipedia.org/wiki/Chocolate_chip_cookie",
     "source": "Wikipedia: Chocolate chip cookie", "license": "CC BY-SA 4.0", "redistributable": True},
    {"slug": "python_docs_tutorial", "url": "https://docs.python.org/3/tutorial/introduction.html",
     "source": "Python 3 documentation: An Informal Introduction to Python",
     "license": "PSF License Agreement", "redistributable": True},
    {"slug": "mdn_css_display", "url": "https://developer.mozilla.org/en-US/docs/Web/CSS/display",
     "source": "MDN Web Docs: CSS display", "license": "CC BY-SA 2.5", "redistributable": True},
    {"slug": "mdn_html_details", "url": "https://developer.mozilla.org/en-US/docs/Web/HTML/Element/details",
     "source": "MDN Web Docs: <details> element", "license": "CC BY-SA 2.5", "redistributable": True},
    {"slug": "weather_gov", "url": "https://www.weather.gov/",
     "source": "US National Weather Service (weather.gov)",
     "license": "US Government work, public domain (17 U.S.C. 105)", "redistributable": True},
    {"slug": "usa_gov", "url": "https://www.usa.gov/",
     "source": "USA.gov", "license": "US Government work, public domain (17 U.S.C. 105)",
     "redistributable": True},
    # ---- local-only (gitignored) ----
    {"slug": "stackoverflow_sorted_array",
     "url": "https://stackoverflow.com/questions/11227809/why-is-processing-a-sorted-array-faster-than-processing-an-unsorted-array",
     "source": "Stack Overflow question thread", "license": "CC BY-SA (user content), local-only",
     "redistributable": False},
    {"slug": "bbc_news_home", "url": "https://www.bbc.com/news",
     "source": "BBC News front page", "license": "All rights reserved, local-only", "redistributable": False},
    {"slug": "apnews_home", "url": "https://apnews.com/",
     "source": "Associated Press front page", "license": "All rights reserved, local-only",
     "redistributable": False},
    {"slug": "allrecipes_home", "url": "https://www.allrecipes.com/",
     "source": "Allrecipes front page", "license": "All rights reserved, local-only",
     "redistributable": False},
    {"slug": "seriouseats_home", "url": "https://www.seriouseats.com/",
     "source": "Serious Eats front page", "license": "All rights reserved, local-only",
     "redistributable": False},
    {"slug": "rei_home", "url": "https://www.rei.com/",
     "source": "REI storefront", "license": "All rights reserved, local-only", "redistributable": False},
    {"slug": "reddit_recipes", "url": "https://old.reddit.com/r/recipes/",
     "source": "Reddit r/recipes (old UI)", "license": "User content, local-only", "redistributable": False},
]


def _freeze(page, css_chunks: list[str]) -> tuple[str, list[str]]:
    """Strip scripts and stylesheet links, inline captured CSS, return (html, third_party_image_hosts)."""
    page_host = urlparse(page.url).hostname or ""
    img_hosts = page.evaluate(
        """() => Array.from(document.images).map(i => { try { return new URL(i.src).host; }
             catch (e) { return ''; } }).filter(Boolean)""")
    third_party = sorted({h for h in img_hosts if h and h != page_host})
    page.evaluate(
        """() => {
             document.querySelectorAll('script').forEach(n => n.remove());
             document.querySelectorAll('link[rel~=\"stylesheet\"]').forEach(n => n.remove());
             document.querySelectorAll('link[rel=\"preload\"][as=\"script\"]').forEach(n => n.remove());
           }""")
    html = page.content()
    combined = "\n".join(c for c in css_chunks if c.strip())
    if combined:
        style = "<style data-inlined-from-network>\n" + combined + "\n</style>"
        html = html.replace("</head>", style + "</head>", 1) if "</head>" in html else style + html
    return html, third_party


def fetch_one(pw, site: dict) -> dict:
    """Return the site dict enriched with status/bytes/third_party, or an 'error' key on failure."""
    browser = pw.chromium.launch()
    try:
        ctx = browser.new_context(user_agent=UA, viewport={"width": 1280, "height": 1000})
        page = ctx.new_page()
        css_chunks: list[str] = []

        def on_response(resp):
            try:
                ct = resp.headers.get("content-type", "")
                if "text/css" in ct or resp.url.split("?")[0].endswith(".css"):
                    css_chunks.append(resp.text())
            except Exception:
                pass

        page.on("response", on_response)
        page.goto(site["url"], wait_until="load", timeout=30000)
        page.wait_for_timeout(2000)
        if not (urlparse(page.url).hostname or ""):
            return {**site, "error": "no final host"}
        html, third_party = _freeze(page, css_chunks)
        out = BENIGN / site["slug"] / "index.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html, encoding="utf-8")
        return {**site, "status": "ok", "bytes": len(html.encode("utf-8")),
                "css_sheets": len([c for c in css_chunks if c.strip()]),
                "third_party_images": third_party, "final_url": page.url}
    except Exception as exc:  # bot wall, timeout, navigation error
        return {**site, "error": f"{type(exc).__name__}: {exc}"[:200]}
    finally:
        browser.close()


def merge_manifest(saved: list[dict]) -> None:
    """Add/replace benign/{slug}/index.html entries; keep evil and the hand-made benign page."""
    saved_paths = {f"benign/{s['slug']}/index.html" for s in saved}
    kept = [e for e in json.loads(MANIFEST.read_text(encoding="utf-8"))
            if e["path"] not in saved_paths]
    entries = [{"path": f"benign/{s['slug']}/index.html", "label": "benign", "technique": None,
                "source": s["source"], "url": s["url"], "license": s["license"],
                "redistributable": s["redistributable"], "expected_layer1": False}
               for s in saved]
    MANIFEST.write_text(json.dumps(kept + entries, indent=2) + "\n", encoding="utf-8")


def write_attribution(saved: list[dict]) -> None:
    lines = ["# Benign corpus attribution",
             "",
             "Real pages saved as frozen, script-stripped offline snapshots for false-positive testing "
             "(R3-T3). Only the redistributable pages below are committed to git; the rest are gitignored "
             "and kept locally only.",
             "",
             "Note: MDN Web Docs prose is CC BY-SA 2.5 (the actual MDN licence), not 4.0.",
             "",
             "## Committed (redistributable)", ""]
    for s in saved:
        if s["redistributable"]:
            tp = s.get("third_party_images") or []
            flag = f"  Third-party images embedded: {', '.join(tp)}." if tp else ""
            lines.append(f"- **{s['source']}** — {s['url']} — {s['license']}.{flag}")
    lines += ["", "## Local-only (gitignored, not committed)", ""]
    for s in saved:
        if not s["redistributable"]:
            lines.append(f"- {s['source']} — {s['url']} — {s['license']}.")
    ATTRIBUTION.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    from playwright.sync_api import sync_playwright
    saved, failed = [], []
    with sync_playwright() as pw:
        for site in SITES:
            res = fetch_one(pw, site)
            if res.get("status") == "ok":
                saved.append(res)
                tp = res.get("third_party_images") or []
                print(f"OK   {res['slug']:<34} {res['bytes']:>8} B  css={res['css_sheets']:<3}"
                      f" 3rd-party-img={len(tp)}")
            else:
                failed.append(res)
                print(f"SKIP {site['slug']:<34} {res.get('error')}")
    if saved:
        merge_manifest(saved)
        write_attribution(saved)
    print(f"\nsaved {len(saved)}  |  failed {len(failed)}")
    print("committed:", [s["slug"] for s in saved if s["redistributable"]])
    print("local-only:", [s["slug"] for s in saved if not s["redistributable"]])


if __name__ == "__main__":
    main()
