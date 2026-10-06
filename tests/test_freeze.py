from __future__ import annotations

from pathlib import Path
import sqlite3
import sys

from forge.cli import main
from test_experiment import manifest_file
from test_scheduler import ready_task, rows
from test_validation import task_repo


def test_final_refuses_without_freeze_then_runs_with_match(tmp_path: Path, task_repo, capsys):
    db = tmp_path / "experiment.sqlite"
    task = ready_task(tmp_path, task_repo, db)
    manifest = manifest_file(tmp_path, task, phase="final", argv=[sys.executable, "-c", "pass"])
    assert main(["run-experiment", str(manifest)]) != 0
    assert "freeze" in capsys.readouterr().out.lower()
    assert rows(db, "runs") == []
    assert main(["freeze", str(manifest), "--db", str(db)]) == 0
    frozen = rows(db, "freezes")
    assert len(frozen) == 1
    assert len(frozen[0]["manifest_sha256"]) == 64
    assert len(frozen[0]["benchmark_hash"]) == 64
    assert frozen[0]["timestamp"]
    assert main(["run-experiment", str(manifest)]) == 0
    assert len(rows(db, "runs")) == 1
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT phase FROM experiments JOIN runs USING (experiment_id)").fetchone()[0] == "final"


def test_changed_manifest_does_not_match_freeze(tmp_path: Path, task_repo, capsys):
    db = tmp_path / "experiment.sqlite"
    task = ready_task(tmp_path, task_repo, db)
    manifest = manifest_file(tmp_path, task, phase="final")
    assert main(["freeze", str(manifest), "--db", str(db)]) == 0
    manifest_file(tmp_path, task, phase="final", seed=21)
    assert main(["run-experiment", str(manifest)]) != 0
    assert "freeze" in capsys.readouterr().out.lower()
    assert rows(db, "runs") == []


def test_pilot_runs_without_freeze(tmp_path: Path, task_repo):
    db = tmp_path / "experiment.sqlite"
    task = ready_task(tmp_path, task_repo, db)
    manifest = manifest_file(tmp_path, task, phase="pilot")
    assert main(["run-experiment", str(manifest)]) == 0
    assert len(rows(db, "runs")) == 1
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT phase FROM experiments").fetchone()[0] == "pilot"
