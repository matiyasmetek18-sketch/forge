from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3

import pytest

from forge.cli import main
from forge.db import _ensure_schema


def synthetic_db(tmp_path: Path, tasks: dict[str, tuple[list[str], list[str]]], *, phase: str = "pilot", tokens=None) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    db = tmp_path / "analysis.sqlite"
    with sqlite3.connect(db) as conn:
        _ensure_schema(conn)
        conn.execute(
            "INSERT INTO experiments (experiment_id, phase, manifest_text, manifest_sha256, benchmark_hash, agent_name, python_version, os, forge_version, start_time) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("exp", phase, "manifest", "manifest-hash", "benchmark-hash", "cmd", "3", "test", "1", "2026-10-06T10:00:00+00:00"),
        )
        position = 0
        for task_id, conditions in tasks.items():
            for condition, statuses in zip(("baseline", "skill"), conditions):
                for trial, status in enumerate(statuses, 1):
                    run_id = f"run-{position}"
                    token_value = tokens(task_id, condition, trial) if tokens else 100
                    conn.execute(
                        "INSERT INTO runs (run_id, experiment_id, task_id, task_version, condition, trial, seed, base_commit, status, protected_paths_modified, start_time, end_time, agent_cmd, stdout_path, stderr_path, forge_version, input_tokens, output_tokens, wall_seconds, command_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (run_id, "exp", task_id, "1", condition, trial, position, "base", status, "[]", "s", "e", "[]", "out", "err", "1", token_value, 0 if token_value is not None else None, 2.0, 3),
                    )
                    conn.execute(
                        "INSERT INTO experiment_runs (experiment_id, task_id, condition, trial, planned_position, run_seed, run_id, attempts) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        ("exp", task_id, condition, trial, position, position, run_id, 2 if status == "infra_error" else 1),
                    )
                    position += 1
    return db


def rule_file(tmp_path: Path, **overrides) -> Path:
    values = {"min_tasks": 1, "min_trials_per_condition": 1}
    values.update(overrides)
    path = tmp_path / "rule.toml"
    path.write_text("".join(f"{key} = {json.dumps(value)}\n" for key, value in values.items()))
    return path


def run_analysis(db: Path, rule: Path | None = None, *, samples: int = 400, seed: int = 42, out: Path | None = None):
    args = ["analyze", "--db", str(db), "--experiment-id", "exp", "--bootstrap-samples", str(samples), "--analysis-seed", str(seed)]
    if rule is not None:
        args += ["--rule", str(rule)]
    if out is not None:
        args += ["--out", str(out)]
    code = main(args)
    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM analyses ORDER BY rowid DESC LIMIT 1").fetchone()
    return code, json.loads(row["report"]) if row else None, row


def qualifying_tasks(n: int = 12, *, base_passes: int = 2, skill_passes: int = 3, trials: int = 5):
    return {
        f"task-{index:02}": (
            ["passed"] * base_passes + ["failed"] * (trials - base_passes),
            ["passed"] * skill_passes + ["failed"] * (trials - skill_passes),
        )
        for index in range(n)
    }


def test_task_level_rates_mean_and_degenerate_ci(tmp_path: Path):
    tasks = {
        "a": (["passed", "failed"], ["passed", "passed"]),
        "b": (["failed", "failed"], ["passed", "failed"]),
    }
    db = synthetic_db(tmp_path, tasks)
    code, report, _ = run_analysis(db, rule_file(tmp_path), samples=200)
    assert code == 0
    assert report["estimate_pp"] == 50
    assert (report["ci_lo_pp"], report["ci_hi_pp"]) == (50, 50)
    assert report["n_tasks"] == 2
    assert [(t["task_id"], t["baseline_rate"], t["skill_rate"], t["delta_pp"], t["baseline_valid"], t["skill_valid"]) for t in report["tasks"]] == [
        ("a", 0.5, 1.0, 50, 2, 2), ("b", 0.0, 0.5, 50, 2, 2),
    ]


def test_bootstrap_is_deterministic_contains_estimate_and_clusters_tasks(tmp_path: Path):
    tasks = {"large": (["failed"] * 100, ["passed"] * 100), "small": (["passed"], ["failed"])}
    db = synthetic_db(tmp_path, tasks)
    rule = rule_file(tmp_path)
    _, first, _ = run_analysis(db, rule, samples=1000, seed=9)
    _, second, _ = run_analysis(db, rule, samples=1000, seed=9)
    assert (first["estimate_pp"], first["ci_lo_pp"], first["ci_hi_pp"]) == (0, -100, 100)
    assert first["ci_lo_pp"] <= first["estimate_pp"] <= first["ci_hi_pp"]
    assert first == second


def test_promotion_rejection_and_inconclusive_boundaries(tmp_path: Path):
    db = synthetic_db(tmp_path / "promote", qualifying_tasks())
    assert run_analysis(db)[1]["verdict"] == "PROMOTE"
    db = synthetic_db(tmp_path / "reject", qualifying_tasks(base_passes=2, skill_passes=2))
    assert run_analysis(db)[1]["verdict"] == "REJECT"
    mixed = qualifying_tasks(base_passes=2, skill_passes=2)
    for task_id in list(mixed)[:6]:
        mixed[task_id] = (["passed"] * 2 + ["failed"] * 3, ["passed"] * 3 + ["failed"] * 2)
    db = synthetic_db(tmp_path / "inconclusive", mixed)
    report = run_analysis(db, samples=2000)[1]
    assert report["ci_lo_pp"] <= 3 <= report["ci_hi_pp"]
    assert report["verdict"] == "INCONCLUSIVE"
    assert "add tasks or trials; do not rerun until significant" in report["reasons"]


def test_token_and_task_drop_guardrails(tmp_path: Path):
    db = synthetic_db(tmp_path / "tokens", qualifying_tasks(), tokens=lambda _t, c, _n: 140 if c == "skill" else 100)
    report = run_analysis(db)[1]
    assert report["telemetry"]["relative_token_change_pct"] == 40
    assert report["verdict"] == "REJECT"
    assert "token_guardrail" in report["reasons"]
    tasks = qualifying_tasks(base_passes=0, skill_passes=5)
    tasks["task-00"] = (["passed"] * 5, ["failed"] * 5)
    db = synthetic_db(tmp_path / "drop", tasks)
    report = run_analysis(db)[1]
    assert report["ci_lo_pp"] > 3
    assert report["verdict"] == "REJECT"
    assert "task_drop_guardrail" in report["reasons"]


def test_infra_excluded_dropped_task_and_unlinked_attempts_reported(tmp_path: Path):
    tasks = {
        "a": (["passed", "infra_error"], ["passed", "failed"]),
        "dropped": (["infra_error"], ["passed"]),
    }
    db = synthetic_db(tmp_path, tasks)
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO runs (run_id, experiment_id, task_id, task_version, condition, trial, seed, base_commit, status, protected_paths_modified, start_time, end_time, agent_cmd, stdout_path, stderr_path, forge_version) VALUES ('retry-old', 'exp', 'a', '1', 'baseline', 2, 2, 'base', 'infra_error', '[]', 's', 'e', '[]', 'out', 'err', '1')"
        )
    _, report, _ = run_analysis(db, rule_file(tmp_path))
    task = report["tasks"][0]
    assert task["task_id"] == "a" and task["baseline_valid"] == 1 and task["baseline_rate"] == 1
    assert report["dropped_tasks"] == ["dropped"]
    assert report["verdict"] == "INCONCLUSIVE"
    assert "dropped_tasks" in report["reasons"]
    assert report["health"]["baseline"]["final_infra_errors"] == 2
    assert report["unlinked_runs"]["infra_error"] == 1


def test_health_and_sample_size_failures_are_inconclusive(tmp_path: Path):
    tasks = qualifying_tasks(n=9)
    report = run_analysis(synthetic_db(tmp_path / "few", tasks))[1]
    assert report["verdict"] == "INCONCLUSIVE" and "insufficient_tasks" in report["reasons"]
    tasks = qualifying_tasks(trials=2, base_passes=1, skill_passes=2)
    report = run_analysis(synthetic_db(tmp_path / "trials", tasks))[1]
    assert report["verdict"] == "INCONCLUSIVE" and "insufficient_trials" in report["reasons"]
    tasks = qualifying_tasks()
    tasks["task-00"][0][0] = "agent_error"
    tasks["task-01"][0][0] = "grader_error"
    report = run_analysis(synthetic_db(tmp_path / "health", tasks))[1]
    assert report["verdict"] == "INCONCLUSIVE" and "health_failure" in report["reasons"]
    assert report["health"]["baseline"]["grader_error"] == 1


def test_null_telemetry_zero_median_and_pilot_warning(tmp_path: Path, capsys):
    db = synthetic_db(tmp_path, qualifying_tasks(), tokens=lambda _t, c, n: None if c == "skill" and n == 1 else (0 if c == "baseline" else 10))
    out = tmp_path / "report.md"
    _, report, _ = run_analysis(db, out=out)
    assert "PILOT (development data): NOT EVIDENCE" in capsys.readouterr().out
    assert "PILOT (development data): NOT EVIDENCE" in out.read_text()
    assert report["telemetry"]["skill"]["missing_tokens"] == 12
    assert report["telemetry"]["relative_token_change_pct"] is None
    assert report["telemetry"]["relative_token_undefined_reason"] == "baseline_median_zero"
    assert report["verdict"] == "PROMOTE"


def test_final_requires_rule_matching_freeze_and_single_shot(tmp_path: Path, capsys):
    db = synthetic_db(tmp_path, qualifying_tasks(), phase="final")
    rule = rule_file(tmp_path)
    assert main(["analyze", "--db", str(db), "--experiment-id", "exp"]) != 0
    assert run_analysis(db, rule)[0] != 0
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO freezes (freeze_id, manifest_sha256, benchmark_hash, skill_sha256, timestamp, rule_sha256, analysis_code_sha256) VALUES ('bad', 'manifest-hash', 'benchmark-hash', NULL, '2026-10-06T09:00:00+00:00', ?, 'wrong-code')",
            (hashlib.sha256(rule.read_bytes()).hexdigest(),),
        )
    assert run_analysis(db, rule)[0] != 0
    from forge.analysis import analysis_code_sha256
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO freezes (freeze_id, manifest_sha256, benchmark_hash, skill_sha256, timestamp, rule_sha256, analysis_code_sha256) VALUES ('good', 'manifest-hash', 'benchmark-hash', NULL, '2026-10-06T09:00:00+00:00', ?, ?)",
            (hashlib.sha256(rule.read_bytes()).hexdigest(), analysis_code_sha256()),
        )
    code, first, _ = run_analysis(db, rule, samples=300, seed=7)
    assert code == 0 and first["verdict"] == "PROMOTE"
    code, second, _ = run_analysis(db, rule, samples=50, seed=999)
    assert code == 0 and second == first
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM analyses").fetchone()[0] == 1
    assert "PROMOTE" in capsys.readouterr().out


def test_final_recomputation_mismatch_fails_loudly(tmp_path: Path, capsys):
    db = synthetic_db(tmp_path, qualifying_tasks(), phase="final")
    rule = rule_file(tmp_path)
    from forge.analysis import analysis_code_sha256
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO freezes (freeze_id, manifest_sha256, benchmark_hash, skill_sha256, timestamp, rule_sha256, analysis_code_sha256) VALUES ('good', 'manifest-hash', 'benchmark-hash', NULL, '2026-10-06T09:00:00+00:00', ?, ?)",
            (hashlib.sha256(rule.read_bytes()).hexdigest(), analysis_code_sha256()),
        )
    assert run_analysis(db, rule)[0] == 0
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE runs SET status='failed' WHERE run_id='run-0'")
    assert main(["analyze", "--db", str(db), "--experiment-id", "exp", "--rule", str(rule)]) != 0
    assert "mismatch" in capsys.readouterr().out.lower()
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM analyses").fetchone()[0] == 1
