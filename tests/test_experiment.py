from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
import sys

import pytest

from forge.cli import main
from test_validation import task_repo, task_file


def manifest_file(tmp_path: Path, task: Path, **overrides) -> Path:
    data = {
        "experiment_id": "study-1", "phase": "pilot", "db": "experiment.sqlite",
        "tasks": [str(task)], "conditions": ["baseline"],
        "trials_per_condition": 1, "seed": 19, "agent": "cmd",
        "argv": [sys.executable, "-c", "pass"],
        "max_total_runs": 10, "max_total_tokens": 1000,
    }
    data.update(overrides)
    if data["agent"] == "codex" and "argv" not in overrides:
        data.pop("argv")
    path = tmp_path / "manifest.toml"
    path.write_text("".join(f"{key} = {json.dumps(value)}\n" for key, value in data.items()))
    return path


def test_manifest_registration_records_provenance(tmp_path: Path, task_repo):
    repo, base, reference = task_repo
    task = task_file(tmp_path, repo, base, reference)
    assert main(["validate-task", str(task), "--db", str(tmp_path / "experiment.sqlite"), "--repeats", "1"]) == 0
    manifest = manifest_file(tmp_path, task)
    assert main(["run-experiment", str(manifest), "--plan-only"]) == 0
    with sqlite3.connect(tmp_path / "experiment.sqlite") as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM experiments").fetchone()
    assert row["experiment_id"] == "study-1"
    assert row["phase"] == "pilot"
    assert row["manifest_text"] == manifest.read_text()
    assert row["manifest_sha256"] == hashlib.sha256(manifest.read_bytes()).hexdigest()
    assert len(row["benchmark_hash"]) == 64
    assert row["agent_name"] == "cmd"
    assert row["model"] is None and row["reasoning_effort"] is None
    assert row["python_version"] and row["os"] and row["forge_version"]


def test_changed_manifest_same_experiment_id_is_rejected(tmp_path: Path, task_repo, capsys):
    repo, base, reference = task_repo
    task = task_file(tmp_path, repo, base, reference)
    assert main(["validate-task", str(task), "--db", str(tmp_path / "experiment.sqlite"), "--repeats", "1"]) == 0
    manifest = manifest_file(tmp_path, task)
    assert main(["run-experiment", str(manifest), "--plan-only"]) == 0
    manifest_file(tmp_path, task, seed=20)
    assert main(["run-experiment", str(manifest), "--plan-only"]) != 0
    assert "invalid_config" in capsys.readouterr().out
    with sqlite3.connect(tmp_path / "experiment.sqlite") as conn:
        assert conn.execute("SELECT COUNT(*) FROM experiments").fetchone()[0] == 1


@pytest.mark.parametrize("overrides", [
    {"phase": "unknown"}, {"conditions": ["other"]}, {"agent": "cmd", "argv": []},
    {"max_total_runs": 0}, {"max_total_tokens": -1}, {"agent": "codex"},
])
def test_manifest_rejects_invalid_configuration(tmp_path: Path, task_repo, overrides, capsys):
    repo, base, reference = task_repo
    task = task_file(tmp_path, repo, base, reference)
    manifest = manifest_file(tmp_path, task, **overrides)
    assert main(["run-experiment", str(manifest), "--plan-only"]) != 0
    assert "invalid_config" in capsys.readouterr().out
