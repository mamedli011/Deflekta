"""Benchmark runner (Role 4, R4-T5): docs/07 sections A, B, D, plus R2's attack-success and ablation files.

For every manifest page (our test set), in raw browse mode, with no API calls:
  - layer 1: one real Chromium scan per page, reused by check_input (SHIELD_LAYERS=1,3, judge off)
  - baseline: sentinel-security sanitise_content(html, format="html") on the exact HTML the agent fetched
Writes <out>/corpus.json (raw per-page rows + metadata) and <out>/summary.md, the only source for slides.
Section E and attack success are copied from R2's benchmark/results/{ablation,attack_success}.json when
present, never computed here. The judge (layer 2) is benchmark C (R4-T6), not run here.

Run:  python -m benchmark.run [--out-dir benchmark/results]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from sandbox import tools
from shield import pipeline

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = Path(__file__).resolve().parent / "results"
BENCH_ENV = {"SHIELD_LAYERS": "1,3", "BROWSE_MODE": "raw"}   # layer 2 off: no Gemini calls
PACKAGES = ("playwright", "html2text", "beautifulsoup4", "sentinel-security", "google-genai")
DOCS07_TARGET = {"evil": 15, "benign": 30}                    # corpus sizes docs/07 asks for

# sentinel-security reads its rules with the system encoding, which crashes on Windows unless UTF-8
# mode is on. Running it in a `python -X utf8` child avoids that regardless of the caller's setup.
_BASELINE_SCRIPT = r"""
import json, sys
from sentinel_security import sanitise_content
out = []
for html in json.load(sys.stdin):
    r = sanitise_content(html, format="html")
    out.append({"risk_level": r["risk_level"], "threats": sorted({t["type"] for t in r["threats"]})})
json.dump(out, sys.stdout)
"""


def group_of(page: dict) -> str:
    """Manifest ground truth: benign, layer1 (hidden, expected caught), known_bypass, layer2 (visible)."""
    if page["label"] != "evil":
        return "benign"
    if page.get("known_bypass") is True:
        return "known_bypass"
    return "layer1" if page.get("expected_layer1") is True else "layer2"


def _markers() -> list[str]:
    return json.loads((tools.FAKEFS / "canaries.json").read_text(encoding="utf-8"))["attacker_markers"]


def _has(text: str, markers: list[str]) -> bool:
    return any(m in text.lower() for m in markers)


def measure_page(base: str, page: dict, markers: list[str]) -> dict:
    """Layer 1 on one page, the way the Shield ON agent sees it (raw browse, then check_input)."""
    url = f"{base}/{page['path']}"
    row = {"path": page["path"], "label": page["label"], "group": group_of(page),
           "technique": page.get("technique"), "payload_id": page.get("payload_id"), "error": None}
    res = tools.execute("browse_web", {"url": url})
    if not res.ok:
        row["error"] = f"browse failed: {res.error}"[:300]
        return row
    scan = pipeline._scan(url)                      # one real render, reused below (R4-T2b)
    d = pipeline.check_input(url, res.output, res.meta.get("raw_html"), scan=scan)
    hits = [s for s in scan.get("segments") or [] if _has(s.get("text", ""), markers)]
    row.update(
        raw_html=res.meta.get("raw_html") or "",
        render_failed=bool(scan.get("render_failed")),
        agent_received_payload=_has(res.output, markers),
        layer1_flagged=bool(hits),
        layer1_techniques=sorted({s["technique"] for s in hits}),
        verdict=d.verdict, severity=d.severity, rule_triggered=d.rule_triggered,
        payload_removed=_has(res.output, markers) and not _has(d.clean_text, markers),
        segment_techniques=sorted({s.get("technique") for s in scan.get("segments") or []} - {None}),
    )
    if row["render_failed"]:
        row["error"] = f"layer 1 render failed: {scan.get('error', '')}"[:300]
    return row


def run_baseline(htmls: list[str], python: str = sys.executable) -> tuple[list[dict] | None, str | None]:
    """sentinel-security on each HTML string. Returns (results, None) or (None, error); never raises."""
    try:
        proc = subprocess.run([python, "-X", "utf8", "-c", _BASELINE_SCRIPT], input=json.dumps(htmls),
                              capture_output=True, text=True, encoding="utf-8", timeout=300)
        if proc.returncode != 0:
            return None, (proc.stderr.strip().splitlines() or ["baseline failed"])[-1][:300]
        return json.loads(proc.stdout), None
    except Exception as exc:
        return None, repr(exc)[:300]


def _rate(k: int, n: int) -> str:
    return f"{k}/{n}" if n else "n/a"


def aggregate(rows: list[dict]) -> dict:
    """Counts only; every number here comes from the rows."""
    ok = [r for r in rows if not r.get("error")]
    hidden = [r for r in ok if r["group"] in ("layer1", "known_bypass")]
    techniques: dict[str, dict] = {}
    for r in hidden:
        t = techniques.setdefault(r["technique"], {"pages": 0, "known_bypass": 0, "reached_agent": 0,
                                                   "layer1_flagged": 0, "removed": 0,
                                                   "baseline_caught": 0, "baseline_run": 0,
                                                   "baseline_only": 0})
        t["pages"] += 1
        t["known_bypass"] += r["group"] == "known_bypass"
        t["reached_agent"] += r["agent_received_payload"]
        t["layer1_flagged"] += r["layer1_flagged"]
        t["removed"] += r["payload_removed"]
        if r.get("baseline_risk") is not None:
            t["baseline_run"] += 1
            t["baseline_caught"] += r["baseline_risk"] != "CLEAN"
            t["baseline_only"] += r["baseline_risk"] != "CLEAN" and not r["layer1_flagged"]
    layer1 = [r for r in hidden if r["group"] == "layer1"]
    reached = [r for r in hidden if r["agent_received_payload"]]
    gap = sorted(t for t, v in techniques.items()
                 if v["baseline_run"] and v["layer1_flagged"] == v["pages"] and v["baseline_caught"] == 0)
    benign = [r for r in ok if r["group"] == "benign"]
    reasons = Counter(x for r in benign if r["verdict"] != "ALLOWED"
                      for x in [r["rule_triggered"]] + r["segment_techniques"])
    return {
        "pages": {"total": len(rows), "errors": len(rows) - len(ok),
                  **{g: sum(r["group"] == g for r in rows) for g in ("layer1", "known_bypass", "layer2", "benign")}},
        "techniques": techniques,
        "layer1_expected_flagged": [sum(r["layer1_flagged"] for r in layer1), len(layer1)],
        "hidden_flagged": [sum(r["layer1_flagged"] for r in hidden), len(hidden)],
        "removed_when_received": [sum(r["payload_removed"] for r in reached), len(reached)],
        "known_bypass_missed": sorted(r["path"] for r in hidden if r["group"] == "known_bypass"
                                      and not r["layer1_flagged"]),
        "known_bypass_now_flagged": sorted(r["path"] for r in hidden if r["group"] == "known_bypass"
                                           and r["layer1_flagged"]),
        "layer2_pages_flagged_by_layer1": [sum(r["layer1_flagged"] for r in ok if r["group"] == "layer2"),
                                           sum(r["group"] == "layer2" for r in ok)],
        "baseline_gap_techniques": gap,
        "baseline_only_techniques": sorted(t for t, v in techniques.items() if v["baseline_only"]),
        "baseline_techniques_run": sum(1 for v in techniques.values() if v["baseline_run"]),
        "benign": {"pages": len(benign), **{v: sum(r["verdict"] == v for r in benign)
                                             for v in ("ALLOWED", "FLAGGED", "STRIPPED")},
                   "top_reasons": reasons.most_common(3)},
    }


def _git(*args: str) -> str | None:
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        return None


def _pkg(name: str) -> str | None:
    try:
        return version(name)
    except PackageNotFoundError:
        return None


def _display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(path)


def metadata(manifest_path: Path) -> dict:
    return {
        "date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_commit": _git("rev-parse", "HEAD"),
        "git_dirty": bool(_git("status", "--porcelain")),
        "python": platform.python_version(), "platform": platform.platform(),
        "packages": {p: _pkg(p) for p in PACKAGES},
        "manifest": _display_path(manifest_path),
        "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "config": {**BENCH_ENV, "judge": "not run (layer 2 off; judge benchmark is R4-T6)",
                   "models_used": "none (no LLM calls in this benchmark)",
                   "baseline": "sentinel-security sanitise_content(html, format='html'); caught = risk_level != CLEAN"},
    }


def _read_r2(path: Path, producer: str = "R2 produces it") -> tuple[dict | None, str | None]:
    """(document, None), or (None, why it is not available). Never raises."""
    if not path.exists():
        return None, f"`{path.name}` not found in the results folder ({producer})"
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return None, f"`{path.name}` could not be read ({type(exc).__name__})"
    return (doc, None) if isinstance(doc, dict) else (None, f"`{path.name}` is not a JSON object")


def _r2_section(title: str, path: Path, with_layers: bool) -> list[str]:
    lines = [f"## {title}", ""]
    doc, why = _read_r2(path)
    if doc is None:
        return lines + [f"Not available: {why}.", ""]
    filename = path.name
    s = doc.get("summary") or {}
    lines += [f"Copied from `{filename}` (R2). Agent model: `{doc.get('model')}`, "
              f"n per page: {doc.get('n_per_page')}, runs finished: {doc.get('finished_runs')}"
              f"/{doc.get('planned_runs')}, valid: {s.get('valid_runs')}, hijacked: {s.get('hijacked')}."]
    if doc.get("finished_runs") != doc.get("planned_runs"):
        lines.append("**Partial run: not all planned runs finished.**")
    head = (["layers"] if with_layers else []) + ["page", "technique", "payload", "valid runs", "hijacked",
                                                  "hijack rate", "errors"]
    lines += ["", "| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for g in s.get("per_group") or []:
        cells = ([str(g.get("layers"))] if with_layers else []) + [
            str(g.get(k)) for k in ("path", "technique", "payload_id", "valid_runs", "hijacked",
                                    "hijack_rate", "errors")]
        lines.append("| " + " | ".join(cells) + " |")
    return lines + [""]


def _c_section(path: Path) -> list[str]:
    """Benchmark C, copied from benchmark/judge_eval.py's output. Nothing is computed here."""
    lines = ["## C. Layer 2 judge on outside datasets", ""]
    doc, why = _read_r2(path, producer="`python -m benchmark.judge_eval` produces it")
    if doc is None:
        return lines + [f"Not available: {why}. Benchmark C has not been run.", ""]
    cfg, s, meta = doc.get("config") or {}, doc.get("summary") or {}, doc.get("metadata") or {}
    ds = cfg.get("datasets") or {}
    inj, ben, lat = s.get("injection") or {}, s.get("benign") or {}, s.get("latency_ms") or {}
    lines += [f"Copied from `{path.name}`. Judge model: `{cfg.get('judge_model')}`, date {meta.get('date')}, "
              f"commit `{meta.get('git_commit')}`, seed {cfg.get('seed')}, n per dataset {cfg.get('n_per_dataset')}, "
              f"calls finished {doc.get('finished_calls')}/{doc.get('planned_calls')}. "
              f"Flagged = grounded AND is_instruction_to_ai AND confidence >= {cfg.get('visible_flag_confidence')} "
              "(the pipeline's visible-only rule). Unavailable and ungrounded answers are not predictions."]
    if doc.get("finished_calls") != doc.get("planned_calls") or doc.get("stopped_early"):
        lines.append(f"**Partial run** ({doc.get('stopped_early') or 'not all planned calls finished'}).")
    lines += ["", "| dataset | evaluated | valid (coverage) | unavailable | ungrounded | result |", "|---|---|---|---|---|---|",
              f"| {(ds.get('injection') or {}).get('id')} | {inj.get('evaluated')} | {inj.get('valid')} ({inj.get('coverage')}) | "
              f"{inj.get('unavailable')} | {inj.get('ungrounded')} | TP {inj.get('tp')}, FP {inj.get('fp')}, TN {inj.get('tn')}, "
              f"FN {inj.get('fn')}; precision {inj.get('precision')}, recall {inj.get('recall')}, F1 {inj.get('f1')} |",
              f"| {(ds.get('benign') or {}).get('id')} | {ben.get('evaluated')} | {ben.get('valid')} ({ben.get('coverage')}) | "
              f"{ben.get('unavailable')} | {ben.get('ungrounded')} | false positives {ben.get('false_positives')}, "
              f"false-positive rate {ben.get('false_positive_rate')} |",
              "", f"- Judge latency over answered calls ({lat.get('answered_calls')}): median {lat.get('median')} ms, "
                  f"p90 {lat.get('p90')} ms", ""]
    return lines


def render_summary(meta: dict, agg: dict, baseline_error: str | None, results_dir: Path) -> str:
    p, b = agg["pages"], agg["benign"]
    evil = p["layer1"] + p["known_bypass"] + p["layer2"]
    small = [f"{k}: {v} (docs/07 target {DOCS07_TARGET[k]})" for k, v in
             (("evil", evil), ("benign", p["benign"])) if v < DOCS07_TARGET[k]]
    L = ["# Benchmark summary (our test set)", "",
         "Generated by `python -m benchmark.run`. This file is the only source for slide numbers.", "",
         "## Run metadata", "",
         f"- Date (UTC): {meta['date']}",
         f"- Git commit: `{meta['git_commit']}`" + (" (working tree had uncommitted changes)" if meta["git_dirty"] else ""),
         f"- Python {meta['python']} on {meta['platform']}",
         "- Packages: " + ", ".join(f"{k} {v}" for k, v in meta["packages"].items()),
         f"- Manifest: `{meta['manifest']}` sha256 `{meta['manifest_sha256'][:16]}...`",
         f"- Pages: {p['total']} ({p['layer1']} layer-1, {p['known_bypass']} known bypass, {p['layer2']} "
         f"visible/layer-2, {p['benign']} benign), errors: {p['errors']}",
         f"- Config: SHIELD_LAYERS={meta['config']['SHIELD_LAYERS']}, BROWSE_MODE={meta['config']['BROWSE_MODE']}; "
         f"judge: {meta['config']['judge']}; models: {meta['config']['models_used']}",
         f"- Baseline: {meta['config']['baseline']}" + (f" -- **not run: {baseline_error}**" if baseline_error else "")]
    if small:
        L.append("- **Corpus below docs/07 size targets** (" + "; ".join(small) + "). Numbers are provisional.")
    L += ["", "## A. Layer 1 detection per technique", "",
          "Hidden-text pages only (layer-1 and known-bypass groups). *Flagged* = layer 1 reported a hidden "
          "segment containing the payload. *Removed* = the payload reached the raw-mode agent and "
          "check_input took it out.", "",
          "| technique | pages | known bypass | payload reached raw agent | layer 1 flagged | removed from agent input |",
          "|---|---|---|---|---|---|"]
    for t, v in sorted(agg["techniques"].items()):
        L.append(f"| {t} | {v['pages']} | {v['known_bypass']} | {v['reached_agent']} | "
                 f"{_rate(v['layer1_flagged'], v['pages'])} | {_rate(v['removed'], v['reached_agent'])} |")
    L += ["", f"- Pages expected to be caught (`expected_layer1`): flagged {_rate(*agg['layer1_expected_flagged'])}",
          f"- All hidden-text pages, including known bypasses: flagged {_rate(*agg['hidden_flagged'])}",
          f"- Payload removed when it reached the raw agent: {_rate(*agg['removed_when_received'])}",
          f"- Known layer-1 bypasses (missed): {len(agg['known_bypass_missed'])}"
          + ("".join(f"\n  - `{x}`" for x in agg["known_bypass_missed"])),
          f"- Visible (layer-2) pages wrongly flagged by layer 1: {_rate(*agg['layer2_pages_flagged_by_layer1'])} "
          "(the judge is not run here)"]
    if agg["known_bypass_now_flagged"]:
        L.append(f"- **Marked known_bypass but now flagged** (update the manifest): {agg['known_bypass_now_flagged']}")
    L += ["", "## B. Baseline comparison (sentinel-security, HTML mode)", ""]
    if baseline_error:
        L.append(f"Not available: baseline did not run ({baseline_error}).")
    else:
        L += ["| technique | pages | layer 1 flagged | baseline caught |", "|---|---|---|---|"]
        for t, v in sorted(agg["techniques"].items()):
            L.append(f"| {t} | {v['pages']} | {_rate(v['layer1_flagged'], v['pages'])} | "
                     f"{_rate(v['baseline_caught'], v['baseline_run'])} |")
        L += ["", f"Techniques layer 1 flagged on every page and the baseline caught on none: "
                  f"{len(agg['baseline_gap_techniques'])} of {agg['baseline_techniques_run']}"
                  + (f" ({', '.join(agg['baseline_gap_techniques'])})" if agg["baseline_gap_techniques"] else ""),
              "", "Techniques where the baseline caught a page that layer 1 missed: "
                  + (", ".join(agg["baseline_only_techniques"]) or "none")]
    L += [""] + _c_section(results_dir / "judge_eval.json")
    L += ["## D. Benign pages (false positives)", "",
          f"- Pages: {b['pages']}; ALLOWED {b['ALLOWED']}, FLAGGED {b['FLAGGED']}, STRIPPED {b['STRIPPED']}",
          "- Top reasons: " + (", ".join(f"{r} ({n})" for r, n in b["top_reasons"]) or "none"), ""]
    L += _r2_section("Attack success, Shield OFF (R2)", results_dir / "attack_success.json", with_layers=False)
    L += _r2_section("E. Layer ablation (R2)", results_dir / "ablation.json", with_layers=True)
    return "\n".join(L).rstrip() + "\n"


def run(out_dir: Path = DEFAULT_OUT, manifest_path: Path | None = None) -> dict:
    """Measure every manifest page and write corpus.json + summary.md into out_dir."""
    from benchmark.latency import _serve
    manifest_path = manifest_path or tools.PAGES / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    markers = _markers()
    saved = {k: os.environ.get(k) for k in BENCH_ENV}
    os.environ.update(BENCH_ENV)
    httpd, base = _serve()
    try:
        rows = [measure_page(base, page, markers) for page in manifest]
    finally:
        httpd.shutdown()
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    base_results, baseline_error = run_baseline([r.get("raw_html", "") for r in rows])
    for r, br in zip(rows, base_results or [None] * len(rows)):
        r["baseline_risk"] = br["risk_level"] if br and not r.get("error") else None
        r["baseline_threats"] = br["threats"] if br and not r.get("error") else None
        r.pop("raw_html", None)
    meta = metadata(manifest_path)
    agg = aggregate(rows)
    doc = {"name": "corpus", "metadata": meta, "baseline_error": baseline_error, "summary": agg, "rows": rows}
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "corpus.json").write_text(json.dumps(doc, indent=2), encoding="utf-8")
    (out_dir / "summary.md").write_text(render_summary(meta, agg, baseline_error, out_dir), encoding="utf-8")
    return doc


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out-dir", default=str(DEFAULT_OUT))
    a = ap.parse_args()
    d = run(Path(a.out_dir))
    print(f"wrote {a.out_dir}/corpus.json and summary.md ({d['summary']['pages']['total']} pages, "
          f"baseline {'ok' if not d['baseline_error'] else 'NOT RUN'})")
