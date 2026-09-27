"""R4-T6 Benchmark C runner: offline only. Fake dataset rows and fake judge answers; no network, no model."""
import json

import pytest

import benchmark.judge_eval as je
from benchmark import run as br
from shield.judge import JudgeUnavailable

SECRET = "sk-test-DO-NOT-LEAK-12345"


def fake_fetch(sizes=None, bad=None):
    """Rows keyed by the pinned parquet URL. deepset rows alternate label 0/1; NotInject rows are prompts."""
    sizes = sizes or {"test": 12, "NotInject_one": 5, "NotInject_two": 5, "NotInject_three": 5}

    def fetch(url):
        for split, n in sizes.items():
            if f"/{split}-" in url or f"data/{split}-" in url:
                if bad == "missing_field":
                    return [{"wrong": "x"}]
                if split == "test":
                    rows = [{"text": f"deepset sample {i}", "label": i % 2} for i in range(n)]
                    if bad == "bad_label":
                        rows[0]["label"] = 7
                    return rows
                return [{"prompt": f"{split} benign prompt {i}", "word_list": ["ignore"], "category": "c"}
                        for i in range(n)]
        raise je.DatasetUnavailable(f"no fake data for {url}")
    return fetch


def verdict(text, instr=True, conf=0.9, grounded=True):
    return {"is_instruction_to_ai": instr, "confidence": conf, "target_action": "x" if instr else None,
            "quoted_span": text if instr else "", "reason": "r", "grounded": grounded, "hidden_complete": True}


def honest_judge(calls=None):
    """Flags exactly the deepset label-1 texts (odd index) at confidence 0.9; benign never flagged."""
    def j(text, hidden):
        if calls is not None:
            calls.append(text)
        assert hidden == []                                             # visible-only evaluation
        instr = text.startswith("deepset") and int(text.split()[-1]) % 2 == 1
        return verdict(text, instr=instr, conf=0.9 if instr else 0.95)
    return j


# ---- data loading and sampling ----

def test_load_rows_uses_verified_fields_and_labels():
    rows = je.load_dataset_rows("injection", fake_fetch())
    assert len(rows) == 12 and rows[1]["id"] == "injection:test:1"
    assert [r["expected_positive"] for r in rows[:4]] == [False, True, False, True]   # 1 = INJECTION
    benign = je.load_dataset_rows("benign", fake_fetch())
    assert len(benign) == 15 and not any(r["expected_positive"] for r in benign)
    assert {r["split"] for r in benign} == {"NotInject_one", "NotInject_two", "NotInject_three"}


@pytest.mark.parametrize("bad", ["missing_field", "bad_label"])
def test_unexpected_schema_fails_cleanly(bad):
    with pytest.raises(je.DatasetUnavailable):
        je.load_dataset_rows("injection", fake_fetch(bad=bad))


def test_fetch_failure_becomes_dataset_unavailable(monkeypatch):
    import requests

    def boom(*a, **k):
        raise requests.ConnectionError("offline")
    monkeypatch.setattr(requests, "get", boom)
    with pytest.raises(je.DatasetUnavailable, match="ConnectionError"):
        je.fetch_parquet("https://example.invalid/x.parquet")


def test_sampling_is_deterministic():
    rows = [{"id": str(i)} for i in range(50)]
    a, b = je.sample(rows, 10, seed=7), je.sample(rows, 10, seed=7)
    assert a == b and len(a) == 10 and [int(r["id"]) for r in a] == sorted(int(r["id"]) for r in a)
    assert je.sample(rows, 10, seed=8) != a
    assert je.sample(rows, 100, seed=7) == rows


# ---- per-sample evaluation ----

ITEM = {"id": "injection:test:3", "kind": "injection", "split": "test", "row_index": 3,
        "text": "deepset sample 3", "expected_positive": True}


@pytest.mark.parametrize("conf,expected", [(0.79, False), (0.8, True), (1.0, True)])
def test_visible_threshold_boundary(conf, expected):
    row = je.evaluate(ITEM, lambda t, h: verdict(t, conf=conf))
    assert row["status"] == "ok" and row["predicted_positive"] is expected
    assert row["raw"]["confidence"] == conf and row["raw"]["is_instruction_to_ai"] is True   # raw kept apart


def test_raw_boolean_alone_is_not_a_prediction():
    row = je.evaluate(ITEM, lambda t, h: verdict(t, instr=False, conf=0.99))
    assert row["predicted_positive"] is False


def test_ungrounded_and_unavailable_are_not_predictions():
    ung = je.evaluate(ITEM, lambda t, h: verdict(t, grounded=False))
    assert ung["status"] == "ungrounded" and ung["predicted_positive"] is None and ung["raw"]["grounded"] is False

    def down(t, h):
        raise JudgeUnavailable("429 quota")
    una = je.evaluate(ITEM, down)
    assert una["status"] == "unavailable" and una["predicted_positive"] is None and una["raw"] is None

    def crash(t, h):
        raise RuntimeError("unexpected")
    assert je.evaluate(ITEM, crash)["status"] == "unavailable"


# ---- metrics ----

def _row(kind, expected, status="ok", predicted=None, latency=100.0, split="test"):
    return {"kind": kind, "expected_positive": expected, "status": status, "predicted_positive": predicted,
            "latency_ms": latency, "split": split}


def test_metrics_from_known_confusion_counts():
    rows = ([_row("injection", True, predicted=True)] * 6 + [_row("injection", False, predicted=True)] * 2
            + [_row("injection", False, predicted=False)] * 7 + [_row("injection", True, predicted=False)] * 3
            + [_row("injection", True, status="unavailable")] * 1 + [_row("injection", False, status="ungrounded")] * 1)
    s = je.summarize(rows)["injection"]
    assert (s["tp"], s["fp"], s["tn"], s["fn"]) == (6, 2, 7, 3)
    assert s["precision"] == 0.75 and s["recall"] == 0.6667 and s["f1"] == round(2 * .75 * .6667 / (.75 + .6667), 4)
    assert (s["evaluated"], s["valid"], s["coverage"]) == (20, 18, 0.9)
    assert (s["unavailable"], s["ungrounded"]) == (1, 1)


def test_undefined_metrics_are_none_not_zero():
    s = je.summarize([_row("injection", False, predicted=False)])["injection"]
    assert s["precision"] is None and s["recall"] is None and s["f1"] is None


def test_false_positive_rate_on_benign():
    rows = ([_row("benign", False, predicted=False, split="NotInject_one")] * 7
            + [_row("benign", False, predicted=True, split="NotInject_two")] * 2
            + [_row("benign", False, status="unavailable", split="NotInject_one")]
            + [_row("benign", False, status="ungrounded", split="NotInject_three")])
    b = je.summarize(rows)["benign"]
    assert (b["evaluated"], b["valid"], b["false_positives"], b["false_positive_rate"]) == (11, 9, 2, 0.2222)
    assert (b["unavailable"], b["ungrounded"]) == (1, 1)
    assert b["false_positives_by_split"] == {"NotInject_one": 0, "NotInject_three": 0, "NotInject_two": 2}


def test_latency_uses_answered_calls_only():
    rows = [_row("injection", True, predicted=True, latency=float(ms)) for ms in range(100, 1100, 100)]
    rows.append(_row("injection", True, status="unavailable", latency=15000.0))    # a timeout isn't an answer
    lat = je.summarize(rows)["latency_ms"]
    assert lat["answered_calls"] == 10 and lat["median"] == 550.0 and lat["p90"] == 910.0


# ---- full runs: resume, early stop, secrets ----

def test_run_end_to_end_and_no_key_in_output(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", SECRET)
    monkeypatch.setenv("JUDGE_MODEL", "judge-model-under-test")

    def leaky(text, hidden):                          # an error message that contains the key
        if text.endswith(" 2"):
            raise JudgeUnavailable(f"bad request for key={SECRET}")
        return honest_judge()(text, hidden)
    out = tmp_path / "judge_eval.json"
    doc = je.run(out, n=10, seed=1, judge_fn=leaky, fetch=fake_fetch())
    raw = out.read_text(encoding="utf-8")
    assert SECRET not in raw and "[redacted]" in raw
    assert doc["planned_calls"] == 20 and doc["finished_calls"] == 20
    assert doc["config"]["judge_model"] == "judge-model-under-test" and doc["config"]["seed"] == 1
    assert doc["config"]["datasets"]["injection"]["revision"] == je.DATASETS["injection"]["revision"]
    assert doc["metadata"]["python"] and "google-genai" in doc["metadata"]["packages"]
    assert all("text" not in r for r in doc["rows"]) and all(len(r["text_sha256"]) == 64 for r in doc["rows"])


def test_resume_after_interruption_without_duplicates(tmp_path):
    out = tmp_path / "judge_eval.json"
    first = []

    def interrupted(text, hidden):
        if len(first) == 7:
            raise KeyboardInterrupt
        first.append(text)
        return honest_judge()(text, hidden)
    with pytest.raises(KeyboardInterrupt):
        je.run(out, n=10, seed=1, judge_fn=interrupted, fetch=fake_fetch())
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert saved["finished_calls"] == 7                          # nothing already done was lost
    second = []
    doc = je.run(out, n=10, seed=1, judge_fn=honest_judge(second), fetch=fake_fetch())
    assert len(second) == 13 and not set(second) & set(first)    # only the rest, none asked twice
    ids = [r["id"] for r in doc["rows"]]
    assert len(ids) == len(set(ids)) == doc["planned_calls"] == 20


def test_unavailable_rows_are_retried_and_replaced(tmp_path):
    out = tmp_path / "judge_eval.json"

    def flaky(text, hidden):
        if text.endswith(" 4"):
            raise JudgeUnavailable("503")
        return honest_judge()(text, hidden)
    je.run(out, n=10, seed=1, judge_fn=flaky, fetch=fake_fetch())
    calls = []
    doc = je.run(out, n=10, seed=1, judge_fn=honest_judge(calls), fetch=fake_fetch())
    assert all(c.endswith(" 4") for c in calls) and calls
    assert all(r["status"] == "ok" for r in doc["rows"]) and len(doc["rows"]) == 20


def test_resume_refuses_a_different_configuration(tmp_path):
    out = tmp_path / "judge_eval.json"
    je.run(out, n=4, seed=1, judge_fn=honest_judge(), fetch=fake_fetch())
    with pytest.raises(SystemExit, match="different configuration"):
        je.run(out, n=4, seed=2, judge_fn=honest_judge(), fetch=fake_fetch())


def test_stops_early_after_consecutive_unavailable(tmp_path):
    calls = []

    def down(text, hidden):
        calls.append(text)
        raise JudgeUnavailable("429 RESOURCE_EXHAUSTED")
    doc = je.run(tmp_path / "j.json", n=10, seed=1, judge_fn=down, fetch=fake_fetch(),
                 max_consecutive_unavailable=3)
    assert len(calls) == 3 and "3 unavailable answers in a row" in doc["stopped_early"]
    assert doc["summary"]["injection"]["valid"] == 0 and doc["summary"]["injection"]["precision"] is None


def test_works_with_the_real_judge_code_path(tmp_path, monkeypatch):
    """The real shield.judge.judge (grounding, validation) with only the model reply scripted."""
    import shield.judge as judge_mod
    monkeypatch.setattr(judge_mod, "_generate", lambda prompt: json.dumps(
        {"is_instruction_to_ai": True, "confidence": 0.9, "target_action": "leak",
         "quoted_span": "deepset sample", "reason": "r"}))
    doc = je.run(tmp_path / "j.json", n=2, seed=1, fetch=fake_fetch())
    assert doc["finished_calls"] == 4
    inj = [r for r in doc["rows"] if r["kind"] == "injection"]
    ben = [r for r in doc["rows"] if r["kind"] == "benign"]
    assert all(r["status"] == "ok" and r["raw"]["grounded"] is True and r["predicted_positive"] for r in inj)
    # The scripted quote "deepset sample" is not in NotInject texts: real grounding marks those ungrounded.
    assert all(r["status"] == "ungrounded" and r["raw"]["grounded"] is False for r in ben)
    assert doc["summary"]["benign"]["ungrounded"] == 2 and doc["summary"]["benign"]["valid"] == 0


# ---- --plan and CLI ----

def test_plan_makes_zero_judge_calls(tmp_path, monkeypatch, capsys):
    import shield.judge as judge_mod
    calls = []
    monkeypatch.setattr(judge_mod, "judge", lambda *a: calls.append(a))
    monkeypatch.setattr(judge_mod, "_generate", lambda *a: calls.append(a))
    monkeypatch.setattr(je, "fetch_parquet", fake_fetch())
    out = tmp_path / "judge_eval.json"
    assert je.main(["--plan", "--n", "10", "--out", str(out)], load_env=False) == 0
    printed = json.loads(capsys.readouterr().out)
    assert calls == [] and not out.exists()
    assert printed["max_judge_calls"] == 20 and "no judge calls" in printed["mode"]
    expected = je.sample(je.load_dataset_rows("injection", fake_fetch()), 10, je.SEED)
    assert printed["available"]["injection"] == {"rows": 12, "sampled": 10,
                                                 "sampled_positive": sum(r["expected_positive"] for r in expected)}
    assert printed["config"]["seed"] == je.SEED


def test_cli_reports_missing_dataset_cleanly(monkeypatch, capsys):
    def offline(url):
        raise je.DatasetUnavailable("could not load: ConnectionError")
    monkeypatch.setattr(je, "fetch_parquet", offline)
    assert je.main(["--plan"], load_env=False) == 2
    assert "dataset unavailable" in capsys.readouterr().err


# ---- benchmark/run.py section C ----

def _summary_md(results_dir):
    rows = [{"path": "evil/a.html", "label": "evil", "group": "layer1", "technique": "t", "error": None,
             "agent_received_payload": True, "layer1_flagged": True, "payload_removed": True, "verdict": "STRIPPED",
             "rule_triggered": "r", "segment_techniques": [], "baseline_risk": "CLEAN"}]
    meta = {"date": "d", "git_commit": "c", "git_dirty": False, "python": "3", "platform": "p", "packages": {},
            "manifest": "m", "manifest_sha256": "0" * 64,
            "config": {"SHIELD_LAYERS": "1,3", "BROWSE_MODE": "raw", "judge": "j", "models_used": "none",
                       "baseline": "b"}}
    return br.render_summary(meta, br.aggregate(rows), None, results_dir)


def test_section_c_not_available_without_results(tmp_path):
    md = _summary_md(tmp_path)
    assert "## C. Layer 2 judge on outside datasets" in md
    assert "`judge_eval.json` not found" in md and "Benchmark C has not been run" in md


def test_section_c_copies_recorded_metrics(tmp_path, monkeypatch):
    monkeypatch.setenv("JUDGE_MODEL", "judge-model-under-test")
    doc = je.run(tmp_path / "judge_eval.json", n=10, seed=1, judge_fn=honest_judge(), fetch=fake_fetch())
    md = _summary_md(tmp_path)
    inj, ben = doc["summary"]["injection"], doc["summary"]["benign"]
    assert "judge-model-under-test" in md and "calls finished 20/20" in md
    assert f"TP {inj['tp']}, FP {inj['fp']}, TN {inj['tn']}, FN {inj['fn']}" in md
    assert f"precision {inj['precision']}, recall {inj['recall']}, F1 {inj['f1']}" in md
    assert f"false-positive rate {ben['false_positive_rate']}" in md
    assert "confidence >= 0.8" in md and "Partial run" not in md


# ---- prompt provenance: results from different judge prompts are never mixed ----

def test_prompt_fingerprint_is_deterministic_sha256_of_the_prompt():
    import hashlib
    import shield.judge as judge_mod
    fp = je.prompt_fingerprint()
    assert fp == je.prompt_fingerprint() == je.prompt_fingerprint(judge_mod.JUDGE_PROMPT)
    assert fp == "sha256:" + hashlib.sha256(judge_mod.JUDGE_PROMPT.encode("utf-8")).hexdigest()
    assert len(fp) == len("sha256:") + 64


def test_changed_prompt_changes_the_fingerprint(monkeypatch):
    import shield.judge as judge_mod
    before = je.prompt_fingerprint()
    assert je.prompt_fingerprint("prompt A") != je.prompt_fingerprint("prompt B")
    monkeypatch.setattr(judge_mod, "JUDGE_PROMPT", judge_mod.JUDGE_PROMPT + " ")   # even one character
    assert je.prompt_fingerprint() != before


def test_fingerprint_recorded_in_output_and_plan(tmp_path, monkeypatch, capsys):
    doc = je.run(tmp_path / "j.json", n=4, seed=1, judge_fn=honest_judge(), fetch=fake_fetch())
    saved = json.loads((tmp_path / "j.json").read_text(encoding="utf-8"))
    assert doc["config"]["judge_prompt_sha256"] == saved["config"]["judge_prompt_sha256"] == je.prompt_fingerprint()
    monkeypatch.setattr(je, "fetch_parquet", fake_fetch())
    assert je.main(["--plan", "--n", "4"], load_env=False) == 0
    assert json.loads(capsys.readouterr().out)["config"]["judge_prompt_sha256"] == je.prompt_fingerprint()


def test_resume_with_same_prompt_is_accepted(tmp_path):
    out = tmp_path / "j.json"
    je.run(out, n=4, seed=1, judge_fn=honest_judge(), fetch=fake_fetch())
    calls = []
    doc = je.run(out, n=4, seed=1, judge_fn=honest_judge(calls), fetch=fake_fetch())
    assert calls == [] and doc["finished_calls"] == doc["planned_calls"] == 8      # nothing re-asked


def test_resume_with_a_different_prompt_is_rejected(tmp_path, monkeypatch):
    import shield.judge as judge_mod
    out = tmp_path / "j.json"
    je.run(out, n=4, seed=1, judge_fn=honest_judge(), fetch=fake_fetch())
    before = out.read_text(encoding="utf-8")
    monkeypatch.setattr(judge_mod, "JUDGE_PROMPT", judge_mod.JUDGE_PROMPT + "\n(revised)")
    calls = []
    with pytest.raises(SystemExit, match="different configuration"):
        je.run(out, n=4, seed=1, judge_fn=honest_judge(calls), fetch=fake_fetch())
    assert calls == [] and out.read_text(encoding="utf-8") == before              # old results untouched


def test_fingerprint_holds_no_secret(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", SECRET)
    doc = je.run(tmp_path / "j.json", n=2, seed=1, judge_fn=honest_judge(), fetch=fake_fetch())
    assert SECRET not in json.dumps(doc["config"]) and SECRET not in (tmp_path / "j.json").read_text(encoding="utf-8")
