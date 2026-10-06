from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from forge.cli import main


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


@pytest.fixture
def task_repo(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "Forge Test")
    git(repo, "config", "user.email", "forge@example.test")
    (repo / "calc.py").write_text("def value():\n    return 0\n")
    (repo / "test_calc.py").write_text(
        "import unittest\nfrom calc import value\n"
        "class TestCalc(unittest.TestCase):\n"
        "    def test_value(self): self.assertEqual(value(), 1)\n"
    )
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "base")
    base = git(repo, "rev-parse", "HEAD")
    (repo / "calc.py").write_text("def value():\n    return 1\n")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "reference")
    reference = git(repo, "rev-parse", "HEAD")
    return repo, base, reference


def task_file(tmp_path: Path, repo: Path, base: str, reference: str | None, grader: list[str] | None = None) -> Path:
    task = tmp_path / f"task-{len(list(tmp_path.glob('task-*.toml')))}.toml"
    fields = {
        "task_id": "sample", "version": "1", "repo_path": str(repo),
        "base_commit": base, "agent_prompt": "Fix value.",
        "grader_cmd": grader or [sys.executable, "-m", "unittest", "discover"],
        "grader_paths": ["test_calc.py"], "agent_timeout_s": 2,
        "grader_timeout_s": 0.4,
    }
    if reference is not None:
        fields["reference_commit"] = reference
    task.write_text("".join(f"{key} = {json.dumps(value)}\n" for key, value in fields.items()))
    return task


def validation_row(db: Path):
    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute("SELECT * FROM task_validations ORDER BY rowid DESC LIMIT 1").fetchone()


def test_valid_task_records_checks_and_repeats(tmp_path: Path, task_repo, capsys):
    repo, base, reference = task_repo
    task = task_file(tmp_path, repo, base, reference)
    db = tmp_path / "validations.sqlite"
    assert main(["validate-task", str(task), "--db", str(db), "--repeats", "2"]) == 0
    row = validation_row(db)
    assert row["overall_ok"] == 1
    assert all(row[name] == 1 for name in ("base_fails", "reference_passes", "protected_diff_empty", "deterministic", "reference_hidden"))
    assert row["repeats"] == 2
    assert row["base_tree_sha"] == git(repo, "rev-parse", f"{base}^{{tree}}")
    assert row["reference_tree_sha"] == git(repo, "rev-parse", f"{reference}^{{tree}}")
    assert len(json.loads(row["details"])["base"]) == 2
    assert "ok" in capsys.readouterr().out


@pytest.mark.parametrize("scenario,expected", [("base_passes", "base_fails"), ("reference_fails", "reference_passes"), ("protected_edit", "protected_diff_empty"), ("protected_rename", "protected_diff_empty")])
def test_validation_rejects_bad_tasks(tmp_path: Path, task_repo, scenario: str, expected: str):
    repo, base, reference = task_repo
    if scenario == "base_passes":
        (repo / "test_calc.py").write_text("import unittest\nclass TestCalc(unittest.TestCase):\n    def test_ok(self): self.assertTrue(True)\n")
        git(repo, "add", "test_calc.py")
        git(repo, "commit", "-qm", "passing base")
        base = git(repo, "rev-parse", "HEAD")
        reference = base
    elif scenario == "reference_fails":
        reference = base
    elif scenario == "protected_edit":
        (repo / "test_calc.py").write_text("import unittest\nclass TestCalc(unittest.TestCase):\n    def test_ok(self): self.assertTrue(True)\n")
        git(repo, "add", "test_calc.py")
        git(repo, "commit", "-qm", "tampered reference")
        reference = git(repo, "rev-parse", "HEAD")
    else:
        git(repo, "mv", "test_calc.py", "checks.py")
        git(repo, "commit", "-qm", "rename protected test")
        reference = git(repo, "rev-parse", "HEAD")
    task = task_file(tmp_path, repo, base, reference)
    db = tmp_path / "bad.sqlite"
    assert main(["validate-task", str(task), "--db", str(db), "--repeats", "1"]) != 0
    row = validation_row(db)
    assert row[expected] == 0
    assert row["overall_ok"] == 0


def test_flaky_grader_and_grader_errors_are_recorded(tmp_path: Path, task_repo):
    repo, base, reference = task_repo
    counter = tmp_path / "counter"
    code = f"from pathlib import Path; p=Path({str(counter)!r}); n=int(p.read_text())+1 if p.exists() else 1; p.write_text(str(n)); raise SystemExit(n%2)"
    task = task_file(tmp_path, repo, base, reference, [sys.executable, "-c", code])
    db = tmp_path / "flaky.sqlite"
    assert main(["validate-task", str(task), "--db", str(db), "--repeats", "2"]) != 0
    assert validation_row(db)["deterministic"] == 0
    for code in ("raise SystemExit(5)", "import time; time.sleep(2)"):
        task = task_file(tmp_path, repo, base, reference, [sys.executable, "-c", code])
        assert main(["validate-task", str(task), "--db", str(db), "--repeats", "1"]) != 0
        details = json.loads(validation_row(db)["details"])
        assert "grader_error" in details["base"]


@pytest.mark.parametrize("reference", [None, "not-a-commit"])
def test_reference_config_errors(tmp_path: Path, task_repo, reference: str | None, capsys):
    repo, base, _ = task_repo
    task = task_file(tmp_path, repo, base, reference)
    assert main(["validate-task", str(task), "--db", str(tmp_path / "invalid.sqlite")]) != 0
    assert "invalid_config" in capsys.readouterr().out


def test_run_once_never_exposes_reference(tmp_path: Path, task_repo):
    repo, base, reference = task_repo
    task = task_file(tmp_path, repo, base, reference)
    agent = tmp_path / "agent.py"
    agent.write_text(
        "import os, pathlib, sys\n"
        "from pathlib import Path\n"
        "needle = sys.argv[1].encode()\n"
        "files = [p for p in Path('.').rglob('*') if p.is_file()]\n"
        "print(needle in str(dict(os.environ)).encode() or needle in os.environ['FORGE_AGENT_PROMPT'].encode() or any(needle in p.read_bytes() for p in files))\n"
    )
    db = tmp_path / "run.sqlite"
    assert main(["run-once", str(task), "--condition", "baseline", "--trial", "1", "--seed", "1", "--experiment-id", "probe", "--db", str(db), "--agent-cmd", sys.executable, str(agent), reference]) == 0
    with sqlite3.connect(db) as conn:
        stdout = conn.execute("SELECT stdout_path FROM runs").fetchone()[0]
    assert Path(stdout).read_text().strip() == "False"


def test_run_once_ignores_invalid_reference_field(tmp_path: Path, task_repo):
    repo, base, _ = task_repo
    task = task_file(tmp_path, repo, base, "not-a-commit")
    db = tmp_path / "run.sqlite"
    agent = tmp_path / "noop.py"
    agent.write_text("pass\n")
    assert main(["run-once", str(task), "--condition", "baseline", "--trial", "1", "--seed", "1", "--experiment-id", "probe", "--db", str(db), "--agent-cmd", sys.executable, str(agent)]) == 0
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT status FROM runs").fetchone()[0] == "failed"
