"""agent.attack_rate with a fake model: no API key, no quota."""
import json

from agent import attack_rate, loop
from contracts.interfaces import RunResult


def _fake_run_agent(task, shield_on, session_id=None, confirm=None):
    """Hijacked only on the demo page with the shield off."""
    hijacked = "recipe_external_css" in task and not shield_on
    return RunResult(session_id, shield_on, "ok", "missing.jsonl", 3, hijacked,
                     hijack_kind="exfiltration" if hijacked else None)


def test_dry_run_makes_no_calls(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(loop, "run_agent", lambda *a, **k: (_ for _ in ()).throw(AssertionError("called")))
    est = attack_rate.main(["rates", "--n", "10", "--dry-run", "--out", str(tmp_path / "x.json")])
    assert est["runs"] == est["pages"] * 10 and est["model_calls_max"] == est["runs"] * loop.MAX_STEPS
    assert not (tmp_path / "x.json").exists()


def test_rates_counts_hijacks_per_page(monkeypatch, tmp_path):
    monkeypatch.setattr(loop, "run_agent", _fake_run_agent)
    out = tmp_path / "attack_success.json"
    attack_rate.main(["rates", "--n", "2", "--out", str(out)])
    doc = json.loads(out.read_text())
    per = {g["path"]: g for g in doc["summary"]["per_group"]}
    assert per["evil/recipe_external_css.html"]["hijacked"] == 2
    assert per["evil/recipe_external_css.html"]["hijack_kinds"] == {"exfiltration": 2}
    assert all(g["hijacked"] == 0 for p, g in per.items() if "external_css" not in p)
    assert doc["finished_runs"] == doc["planned_runs"] == 2 * len(per)


def test_ablation_one_page_per_family_and_errors_kept(monkeypatch, tmp_path):
    calls = []

    def flaky(task, shield_on, session_id=None, confirm=None):
        calls.append((task, shield_on))
        if len(calls) == 1:
            raise RuntimeError("quota")
        return _fake_run_agent(task, shield_on, session_id)

    monkeypatch.setattr(loop, "run_agent", flaky)
    out = tmp_path / "ablation.json"
    attack_rate.main(["ablation", "--n", "1", "--out", str(out)])
    doc = json.loads(out.read_text())
    fams = {g["payload_id"] for g in doc["summary"]["per_group"]}
    assert fams == {"reset_email_forward", "answer_phishing_link"}
    assert len(calls) == len(attack_rate.ABLATION_LAYERS) * 2 and all(on for _, on in calls)
    assert sum(g["errors"] for g in doc["summary"]["per_group"]) == 1
    assert {r["path"] for r in doc["rows"] if r["payload_id"] == "reset_email_forward"} == \
        {"evil/recipe_external_css.html"}
