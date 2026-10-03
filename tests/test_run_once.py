from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import textwrap

import pytest

from forge.runner import RunOnceRequest, run_once


@pytest.fixture
def tiny_repo(tmp_path: Path) -> dict[str, Path | str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _run(["git", "init"], repo)
    _run(["git", "config", "user.email", "forge@example.test"], repo)
    _run(["git", "config", "user.name", "Forge Test"], repo)
    (repo / "calc.py").write_text(
        "def add_one(value):\n    return value\n",
        encoding="utf-8",
    )
    (repo / "test_calc.py").write_text(
        "from calc import add_one\n\n\ndef test_add_one():\n    assert add_one(1) == 2\n",
        encoding="utf-8",
    )
    _run(["git", "add", "."], repo)
    _run(["git", "commit", "-m", "base"], repo)
    base_commit = _run(["git", "rev-parse", "HEAD"], repo).stdout.strip()
    return {"repo": repo, "base_commit": base_commit}


def test_agent_fixes_bug_records_pass_and_cleans_worktree(tmp_path: Path, tiny_repo: dict[str, Path | str]) -> None:
    agent = _agent(tmp_path, "Path('calc.py').write_text('def add_one(value):\\n    return value + 1\\n')")
    result, row = _run_forge(tmp_path, tiny_repo, agent)

    assert result.status == "passed"
    assert row["status"] == "passed"
    assert row["agent_exit_code"] == 0
    assert row["grader_exit_code"] == 0
    assert json.loads(row["protected_paths_modified"]) == []
    assert Path(row["stdout_path"]).exists()
    assert Path(row["stderr_path"]).exists()
    _assert_canonical_clean(tiny_repo["repo"])


def test_agent_does_nothing_fails(tmp_path: Path, tiny_repo: dict[str, Path | str]) -> None:
    agent = _agent(tmp_path, "pass")
    result, row = _run_forge(tmp_path, tiny_repo, agent)

    assert result.status == "failed"
    assert row["grader_exit_code"] == 1
    _assert_canonical_clean(tiny_repo["repo"])


def test_agent_cannot_hide_failure_by_deleting_protected_test(tmp_path: Path, tiny_repo: dict[str, Path | str]) -> None:
    agent = _agent(tmp_path, "Path('test_calc.py').unlink()")
    result, row = _run_forge(tmp_path, tiny_repo, agent)

    assert result.status == "failed"
    assert json.loads(row["protected_paths_modified"]) == ["test_calc.py"]
    _assert_canonical_clean(tiny_repo["repo"])


def test_agent_timeout_is_recorded_and_cleaned(tmp_path: Path, tiny_repo: dict[str, Path | str]) -> None:
    agent = _agent(tmp_path, "import time\ntime.sleep(5)")
    result, row = _run_forge(tmp_path, tiny_repo, agent, agent_timeout_s=0.2)

    assert result.status == "agent_timeout"
    assert row["agent_exit_code"] is None
    assert row["grader_exit_code"] == 1
    _assert_canonical_clean(tiny_repo["repo"])


def test_agent_error_is_graded_and_recorded(tmp_path: Path, tiny_repo: dict[str, Path | str]) -> None:
    agent = _agent(
        tmp_path,
        "Path('calc.py').write_text('def add_one(value):\\n    return value + 1\\n')\nraise SystemExit(3)",
    )
    result, row = _run_forge(tmp_path, tiny_repo, agent)

    assert result.status == "agent_error"
    assert row["agent_exit_code"] == 3
    assert row["grader_exit_code"] == 0
    _assert_canonical_clean(tiny_repo["repo"])


def test_grader_crash_and_timeout_are_grader_error(tmp_path: Path, tiny_repo: dict[str, Path | str]) -> None:
    crashing = _agent(tmp_path, "pass", name="noop.py")
    crash_result, crash_row = _run_forge(
        tmp_path,
        tiny_repo,
        crashing,
        grader_cmd=[sys.executable, "-c", "raise SystemExit(5)"],
    )
    assert crash_result.status == "grader_error"
    assert crash_row["grader_exit_code"] == 5

    timeout_result, timeout_row = _run_forge(
        tmp_path,
        tiny_repo,
        crashing,
        grader_cmd=[sys.executable, "-c", "import time; time.sleep(5)"],
        grader_timeout_s=0.2,
    )
    assert timeout_result.status == "grader_error"
    assert timeout_row["grader_exit_code"] is None
    _assert_canonical_clean(tiny_repo["repo"])


def test_invalid_task_toml_and_bad_commit_are_invalid_config(tmp_path: Path, tiny_repo: dict[str, Path | str]) -> None:
    missing = tmp_path / "missing.toml"
    missing.write_text("task_id = 'bad'\n", encoding="utf-8")
    missing_result = run_once(
        RunOnceRequest(
            task_path=missing,
            condition="baseline",
            trial=1,
            seed=1,
            experiment_id="exp",
            db_path=tmp_path / "missing.sqlite",
            agent_cmd=[sys.executable, "-c", "pass"],
        )
    )
    assert missing_result.status == "invalid_config"

    agent = _agent(tmp_path, "pass")
    bad_result, bad_row = _run_forge(tmp_path, tiny_repo, agent, base_commit="not-a-commit")
    assert bad_result.status == "invalid_config"
    assert bad_row["task_id"] == "unknown"
    _assert_canonical_clean(tiny_repo["repo"])


def test_schema_idempotent_and_fields_round_trip(tmp_path: Path, tiny_repo: dict[str, Path | str]) -> None:
    db = tmp_path / "runs.sqlite"
    agent = _agent(tmp_path, "pass")
    first, _ = _run_forge(tmp_path, tiny_repo, agent, db=db, trial=1)
    second, row = _run_forge(tmp_path, tiny_repo, agent, db=db, trial=2)

    with sqlite3.connect(db) as conn:
        count = conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
        version = conn.execute("PRAGMA user_version").fetchone()[0]

    assert first.run_id != second.run_id
    assert count == 2
    assert version == 1
    assert row["condition"] == "baseline"
    assert row["trial"] == 2
    assert row["seed"] == 99
    assert json.loads(row["agent_cmd"])[0] == sys.executable
    _assert_canonical_clean(tiny_repo["repo"])


def test_cli_run_once_prints_run_id_and_status(tmp_path: Path, tiny_repo: dict[str, Path | str]) -> None:
    agent = _agent(tmp_path, "Path('calc.py').write_text('def add_one(value):\\n    return value + 1\\n')")
    task = _task_file(tmp_path, tiny_repo)
    db = tmp_path / "cli.sqlite"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "forge.cli",
            "run-once",
            str(task),
            "--condition",
            "baseline",
            "--trial",
            "1",
            "--seed",
            "123",
            "--experiment-id",
            "cli-exp",
            "--db",
            str(db),
            "--agent-cmd",
            sys.executable,
            str(agent),
        ],
        cwd=tmp_path,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    )

    run_id, status = result.stdout.strip().split()
    assert len(run_id) == 36
    assert status == "passed"
    _assert_canonical_clean(tiny_repo["repo"])


def _run_forge(
    tmp_path: Path,
    tiny_repo: dict[str, Path | str],
    agent: Path,
    *,
    db: Path | None = None,
    base_commit: str | None = None,
    agent_timeout_s: float = 3,
    grader_timeout_s: float = 3,
    grader_cmd: list[str] | None = None,
    trial: int = 1,
) -> tuple[object, sqlite3.Row]:
    task = _task_file(
        tmp_path,
        tiny_repo,
        base_commit=base_commit,
        agent_timeout_s=agent_timeout_s,
        grader_timeout_s=grader_timeout_s,
        grader_cmd=grader_cmd,
    )
    db_path = db or (tmp_path / "runs.sqlite")
    result = run_once(
        RunOnceRequest(
            task_path=task,
            condition="baseline",
            trial=trial,
            seed=99,
            experiment_id="exp",
            db_path=db_path,
            agent_cmd=[sys.executable, str(agent)],
        )
    )
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM runs WHERE run_id = ?",
            (result.run_id,),
        ).fetchone()
    return result, row


def _task_file(
    tmp_path: Path,
    tiny_repo: dict[str, Path | str],
    *,
    base_commit: str | None = None,
    agent_timeout_s: float = 3,
    grader_timeout_s: float = 3,
    grader_cmd: list[str] | None = None,
) -> Path:
    command = grader_cmd or [sys.executable, "-m", "pytest", "-q"]
    task = tmp_path / f"task-{len(list(tmp_path.glob('task-*.toml')))}.toml"
    task.write_text(
        textwrap.dedent(
            f"""
            task_id = "tiny"
            version = "1"
            repo_path = {str(tiny_repo["repo"])!r}
            base_commit = {base_commit or str(tiny_repo["base_commit"])!r}
            agent_prompt = "Fix add_one."
            grader_cmd = {command!r}
            grader_paths = ["test_calc.py"]
            agent_timeout_s = {agent_timeout_s}
            grader_timeout_s = {grader_timeout_s}
            """
        ),
        encoding="utf-8",
    )
    return task


def _agent(tmp_path: Path, body: str, *, name: str = "agent.py") -> Path:
    path = tmp_path / name
    path.write_text(
        "from pathlib import Path\n" + body + "\n",
        encoding="utf-8",
    )
    return path


def _run(argv: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    )


def _assert_canonical_clean(repo: object) -> None:
    repo_path = Path(repo)
    status = _run(["git", "status", "--short"], repo_path).stdout.strip()
    worktrees = _run(["git", "worktree", "list", "--porcelain"], repo_path).stdout
    assert status == ""
    assert worktrees.count("worktree ") == 1
