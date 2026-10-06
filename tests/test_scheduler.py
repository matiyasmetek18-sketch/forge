from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import sys

from forge.cli import main
from test_experiment import manifest_file
from test_validation import task_repo, task_file
from test_run_once import _codex_stub


def ready_task(tmp_path: Path, task_repo, db: Path, *, task_id: str = "sample") -> Path:
    repo, base, reference = task_repo
    grader = [sys.executable, "-c", "from pathlib import Path; raise SystemExit(0 if 'return 1' in Path('calc.py').read_text() else 1)"]
    task = task_file(tmp_path, repo, base, reference, grader)
    if task_id != "sample":
        task.write_text(task.read_text().replace('task_id = "sample"', f'task_id = "{task_id}"'))
    assert main(["validate-task", str(task), "--db", str(db), "--repeats", "1"]) == 0
    return task


def rows(db: Path, table: str):
    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall()


def test_plan_only_is_deterministic_and_interleaved(tmp_path: Path, task_repo):
    db = tmp_path / "experiment.sqlite"
    task = ready_task(tmp_path, task_repo, db)
    skill = tmp_path / "SKILL.md"
    skill.write_text("Inspect first.\n")
    manifest = manifest_file(tmp_path, task, conditions=["baseline", "skill"], skill=str(skill), trials_per_condition=4)
    assert main(["run-experiment", str(manifest), "--plan-only"]) == 0
    first = [(r["task_id"], r["condition"], r["trial"], r["planned_position"], r["run_seed"]) for r in rows(db, "experiment_runs")]
    assert len(first) == 8
    assert [item[1] for item in first] in (["baseline", "skill"] * 4, ["skill", "baseline"] * 4)
    assert [item[3] for item in first] == list(range(8))
    assert len({item[4] for item in first}) == 8
    assert rows(db, "runs") == []
    assert main(["run-experiment", str(manifest), "--plan-only"]) == 0
    assert first == [(r["task_id"], r["condition"], r["trial"], r["planned_position"], r["run_seed"]) for r in rows(db, "experiment_runs")]


def test_resume_limit_and_prompt_parity(tmp_path: Path, task_repo):
    db = tmp_path / "experiment.sqlite"
    task = ready_task(tmp_path, task_repo, db)
    skill = tmp_path / "SKILL.md"
    skill.write_text("Inspect first.\n")
    agent = tmp_path / "agent.py"
    agent.write_text("import os; print(os.environ['FORGE_AGENT_PROMPT'])\n")
    manifest = manifest_file(tmp_path, task, conditions=["baseline", "skill"], skill=str(skill), argv=[sys.executable, str(agent)], trials_per_condition=1)
    assert main(["run-experiment", str(manifest), "--limit", "1"]) == 0
    assert len(rows(db, "runs")) == 1
    assert main(["run-experiment", str(manifest), "--limit", "1"]) == 0
    assert len(rows(db, "runs")) == 2
    assert main(["run-experiment", str(manifest)]) == 0
    assert len(rows(db, "runs")) == 2
    run_rows = rows(db, "runs")
    assert {row["condition"] for row in run_rows} == {"baseline", "skill"}
    assert len({row["agent_cmd"] for row in run_rows}) == 1
    prompts = {row["condition"]: row["final_prompt"] for row in run_rows}
    assert prompts["baseline"] == "Fix value."
    assert "Inspect first." in prompts["skill"]
    assert all(row["status"] == "failed" for row in run_rows)


def test_preflight_refuses_unvalidated_and_stale_tasks(tmp_path: Path, task_repo, capsys):
    repo, base, reference = task_repo
    task = task_file(tmp_path, repo, base, reference)
    manifest = manifest_file(tmp_path, task)
    assert main(["run-experiment", str(manifest), "--plan-only"]) != 0
    assert "sample" in capsys.readouterr().out
    assert main(["validate-task", str(task), "--db", str(tmp_path / "experiment.sqlite"), "--repeats", "1"]) == 0
    task.write_text(task.read_text() + "\n# changed after validation\n")
    assert main(["run-experiment", str(manifest), "--plan-only"]) != 0
    assert "sample" in capsys.readouterr().out
    assert rows(tmp_path / "experiment.sqlite", "runs") == []


def test_budget_stops_and_null_telemetry_counts_only_runs(tmp_path: Path, task_repo, capsys):
    db = tmp_path / "experiment.sqlite"
    task = ready_task(tmp_path, task_repo, db)
    manifest = manifest_file(tmp_path, task, trials_per_condition=3, max_total_runs=1)
    assert main(["run-experiment", str(manifest)]) == 0
    assert len(rows(db, "runs")) == 1
    assert "max_total_runs" in capsys.readouterr().out
    assert main(["run-experiment", str(manifest)]) == 0
    assert len(rows(db, "runs")) == 1


def test_infra_error_retried_once_and_agent_error_stands(tmp_path: Path, task_repo):
    db = tmp_path / "experiment.sqlite"
    task = ready_task(tmp_path, task_repo, db)
    manifest = manifest_file(tmp_path, task, argv=[str(tmp_path / "missing-agent")])
    assert main(["run-experiment", str(manifest), "--limit", "1"]) == 0
    assert [r["status"] for r in rows(db, "runs")] == ["infra_error"]
    assert main(["run-experiment", str(manifest), "--limit", "1"]) == 0
    assert [r["status"] for r in rows(db, "runs")] == ["infra_error", "infra_error"]
    assert main(["run-experiment", str(manifest)]) == 0
    assert len(rows(db, "runs")) == 2
    assert rows(db, "experiment_runs")[0]["attempts"] == 2

    other = tmp_path / "other"
    other.mkdir()
    task2 = ready_task(other, task_repo, other / "experiment.sqlite")
    manifest2 = manifest_file(other, task2, argv=[sys.executable, "-c", "raise SystemExit(3)"])
    assert main(["run-experiment", str(manifest2)]) == 0
    assert main(["run-experiment", str(manifest2)]) == 0
    assert [r["status"] for r in rows(other / "experiment.sqlite", "runs")] == ["agent_error"]


def test_one_failed_run_does_not_abort_other_planned_runs(tmp_path: Path, task_repo):
    db = tmp_path / "experiment.sqlite"
    task = ready_task(tmp_path, task_repo, db)
    manifest = manifest_file(tmp_path, task, trials_per_condition=2)
    assert main(["run-experiment", str(manifest)]) == 0
    assert [r["status"] for r in rows(db, "runs")] == ["failed", "failed"]


def test_token_budget_stops_after_recorded_usage(tmp_path: Path, task_repo, capsys):
    db = tmp_path / "experiment.sqlite"
    task = ready_task(tmp_path, task_repo, db)
    auth = tmp_path / "auth.json"
    auth.write_text('{"token":"sentinel-auth-value-1234567890"}')
    stub = _codex_stub(tmp_path, "print(json.dumps({'type':'turn.completed','usage':{'input_tokens':8,'cached_input_tokens':0,'output_tokens':8}}))")
    manifest = manifest_file(tmp_path, task, agent="codex", model="gpt-test", reasoning_effort="low", codex_bin=str(stub), codex_auth=str(auth), trials_per_condition=3, max_total_tokens=10)
    assert main(["run-experiment", str(manifest)]) == 0
    assert len(rows(db, "runs")) == 1
    assert rows(db, "runs")[0]["input_tokens"] == 8
    assert "max_total_tokens" in capsys.readouterr().out


def test_missing_codex_auth_stops_before_agent(tmp_path: Path, task_repo, capsys):
    db = tmp_path / "experiment.sqlite"
    task = ready_task(tmp_path, task_repo, db)
    stub = _codex_stub(tmp_path, "raise AssertionError('must not run')")
    manifest = manifest_file(tmp_path, task, agent="codex", model="gpt-test", reasoning_effort="low", codex_bin=str(stub), codex_auth=str(tmp_path / "missing-auth.json"))
    assert main(["run-experiment", str(manifest)]) != 0
    assert "credential_error" in capsys.readouterr().out
    assert rows(db, "runs") == []
