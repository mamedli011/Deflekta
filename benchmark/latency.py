"""Shield latency benchmark (Role 4). Measurement only: how much time does Shield ON add to a page load?

No API key needed: the judge (layer 2) is switched off with SHIELD_LAYERS=1,3, so this measures the
browser + shield processing, not Gemini. Serves sandbox/pages itself on a random local port.

For every manifest page, each repetition times (time.perf_counter, interleaved so drift hits both):
  off          browse_web raw                                   (what Shield OFF costs)
  on           browse_web raw + check_input                     (what Shield ON costs)
  scan         the layer-1 Chromium scan inside that check_input (pipeline._scan)
  rest         check_input minus scan: html2text of the human view, gap, strip, decision
  launch       Chromium start + close, no page                  (fixed cost of a fresh browser)
  load         Chromium start + goto(networkidle) + close       (fixed cost + page load, no scan work)
  overhead     on - off, paired within the same repetition      (what Shield ON adds)
One warm-up round per page is discarded. Reports median and p90 per page and overall.

Run:  python -m benchmark.latency [--reps 10] [--out benchmark/results/latency.json]
Numbers are machine-dependent. Not for slides until they are copied into summary.md on purpose.
"""
from __future__ import annotations

import argparse
import http.server
import json
import os
import platform
import statistics
import threading
import time
from datetime import datetime, timezone
from functools import partial
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from sandbox import tools
from shield import pipeline

METRICS = ["off", "on", "scan", "rest", "launch", "load", "overhead"]
# Layer 2 off: no Gemini calls, no API key needed. Raw browse, as in the default demo setup.
BENCH_ENV = {"SHIELD_LAYERS": "1,3", "BROWSE_MODE": "raw"}
DEFAULT_OUT = Path(__file__).resolve().parent / "results" / "latency.json"


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args) -> None:
        pass


def _serve() -> tuple[http.server.ThreadingHTTPServer, str]:
    handler = partial(_QuietHandler, directory=str(tools.PAGES))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}"


def _ms(t0: float) -> float:
    return (time.perf_counter() - t0) * 1000


def _time_launch() -> float:
    from playwright.sync_api import sync_playwright
    t0 = time.perf_counter()
    with sync_playwright() as p:
        p.chromium.launch().close()
    return _ms(t0)


def _time_load(url: str) -> float:
    from playwright.sync_api import sync_playwright
    t0 = time.perf_counter()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            browser.new_page().goto(url, wait_until="networkidle", timeout=10_000)
        finally:
            browser.close()
    return _ms(t0)


def _one_rep(url: str) -> dict:
    """One interleaved measurement of every metric for one page."""
    t0 = time.perf_counter()
    off_res = tools.execute("browse_web", {"url": url})
    off = _ms(t0)

    scan_ms: list[float] = []
    real_scan = pipeline._scan

    def timed_scan(u: str) -> dict:
        s0 = time.perf_counter()
        try:
            return real_scan(u)
        finally:
            scan_ms.append(_ms(s0))

    pipeline._scan = timed_scan
    try:
        t0 = time.perf_counter()
        res = tools.execute("browse_web", {"url": url})
        browse_ms = _ms(t0)
        c0 = time.perf_counter()
        d = pipeline.check_input(url, res.output, res.meta.get("raw_html"))
        check_ms = _ms(c0)
    finally:
        pipeline._scan = real_scan

    scan = sum(scan_ms)
    on = browse_ms + check_ms
    return {"off": off, "on": on, "overhead": on - off, "scan": scan, "rest": check_ms - scan,
            "launch": _time_launch(), "load": _time_load(url),
            "verdict": d.verdict, "render_failed": d.render_failed, "ok": off_res.ok and res.ok}


def _stats(values: list[float]) -> dict:
    ordered = sorted(values)
    p90 = statistics.quantiles(ordered, n=10, method="inclusive")[-1] if len(ordered) > 1 else ordered[0]
    return {"median": round(statistics.median(ordered), 1), "p90": round(p90, 1),
            "min": round(ordered[0], 1), "max": round(ordered[-1], 1), "n": len(ordered)}


def _pkg(name: str) -> str | None:
    try:
        return version(name)
    except PackageNotFoundError:
        return None


def run(reps: int) -> dict:
    """Measure every manifest page. Sets BENCH_ENV only while running, then restores it."""
    manifest = json.loads((tools.PAGES / "manifest.json").read_text(encoding="utf-8"))
    saved = {k: os.environ.get(k) for k in BENCH_ENV}
    os.environ.update(BENCH_ENV)
    httpd, base = _serve()
    try:
        pages = []
        for item in manifest:
            url = f"{base}/{item['path']}"
            _one_rep(url)                                   # warm-up, discarded
            samples = [_one_rep(url) for _ in range(reps)]
            pages.append({
                "path": item["path"], "label": item["label"], "technique": item.get("technique"),
                "verdicts": sorted({s["verdict"] for s in samples}),
                "render_failed": any(s["render_failed"] for s in samples),
                "fetch_ok": all(s["ok"] for s in samples),
                "stats": {m: _stats([s[m] for s in samples]) for m in METRICS},
                "raw_ms": {m: [round(s[m], 1) for s in samples] for m in METRICS},
            })
            print(f"  measured {item['path']}", flush=True)
    finally:
        httpd.shutdown()
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    pooled = {m: _stats([v for p in pages for v in p["raw_ms"][m]]) for m in METRICS}
    return {
        "name": "latency",
        "note": "Measurement only. Machine-dependent. Layer 2 (judge) off. Raw browse mode.",
        "date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "machine": {"platform": platform.platform(), "python": platform.python_version(),
                    "cpu_count": os.cpu_count()},
        "packages": {p: _pkg(p) for p in ("playwright", "html2text", "beautifulsoup4")},
        "config": {"reps": reps, "warmup_rounds": 1, **BENCH_ENV},
        "pages": pages,
        "summary": {
            "pooled": pooled,
            "overhead_median_ms": pooled["overhead"]["median"],
            "overhead_p90_ms": pooled["overhead"]["p90"],
        },
    }


def _print(result: dict) -> None:
    print(f"\n{'page':42} {'metric':7} {'median':>8} {'p90':>8}   (ms)")
    for p in result["pages"]:
        for m in METRICS:
            s = p["stats"][m]
            print(f"{p['path'] if m == 'off' else '':42} {m:7} {s['median']:8.1f} {s['p90']:8.1f}")
        print(f"{'':42} verdicts={p['verdicts']} render_failed={p['render_failed']}")
    s = result["summary"]
    print("\nAll pages pooled:")
    for m in METRICS:
        print(f"  {m:7} median {s['pooled'][m]['median']:8.1f}   p90 {s['pooled'][m]['p90']:8.1f}")
    print(f"  Shield ON - OFF overhead (paired per run): median {s['overhead_median_ms']} ms, "
          f"p90 {s['overhead_p90_ms']} ms")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--reps", type=int, default=10)
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    a = ap.parse_args()
    out = run(max(2, a.reps))
    _print(out)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nwrote {a.out}")
