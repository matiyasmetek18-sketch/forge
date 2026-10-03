from __future__ import annotations

from contextlib import contextmanager
import json
import os
import time
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import textwrap

import pytest

import forge.checkout as checkout_module
import forge.db as db_module
import forge.runner as runner_module
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


def test_agent_fixes_bug_records_pass_and_cleans_clone(tmp_path: Path, tiny_repo: dict[str, Path | str]) -> None:
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


def test_agent_timeout_is_recorded_and_cleans_clone(tmp_path: Path, tiny_repo: dict[str, Path | str]) -> None:
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


@pytest.mark.parametrize("code", [2, 5, 7])
def test_grader_other_exit_codes_are_errors(tmp_path: Path, tiny_repo: dict[str, Path | str], code: int) -> None:
    agent = _agent(tmp_path, "pass")
    result, row = _run_forge(tmp_path, tiny_repo, agent, grader_cmd=[sys.executable, "-c", f"raise SystemExit({code})"])
    assert result.status == "grader_error"
    assert row["grader_exit_code"] == code
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


def test_malformed_toml_is_invalid_config(tmp_path: Path, tiny_repo: dict[str, Path | str]) -> None:
    malformed = tmp_path / "malformed.toml"
    malformed.write_text("task_id = [\n")
    result = run_once(RunOnceRequest(malformed, "baseline", 1, 99, "exp", tmp_path / "malformed.sqlite", [sys.executable, "-c", "pass"]))
    with sqlite3.connect(tmp_path / "malformed.sqlite") as conn:
        assert conn.execute("SELECT status FROM runs").fetchall() == [("invalid_config",)]
    assert result.status == "invalid_config"
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
    assert row["run_id"] == second.run_id
    assert row["experiment_id"] == "exp"
    assert row["task_id"] == "tiny"
    assert row["task_version"] == "1"
    assert row["base_commit"] == tiny_repo["base_commit"]
    assert row["status"] == "failed"
    assert row["agent_exit_code"] == 0
    assert row["grader_exit_code"] == 1
    assert json.loads(row["protected_paths_modified"]) == []
    assert row["start_time"] <= row["end_time"]
    assert Path(row["stdout_path"]).exists()
    assert Path(row["stderr_path"]).exists()
    assert row["forge_version"]
    assert not hasattr(db_module, "update_run")
    assert not hasattr(db_module, "delete_run")
    _assert_canonical_clean(tiny_repo["repo"])


def test_cli_run_once_prints_run_id_and_status(tmp_path: Path, tiny_repo: dict[str, Path | str]) -> None:
    agent = _agent(tmp_path, "Path('calc.py').write_text('def add_one(value):\\n    return value + 1\\n')")
    task = _task_file(tmp_path, tiny_repo)
    db = tmp_path / "cli.sqlite"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    clones_before = _clone_roots()

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
    assert _clone_roots() == clones_before
    _assert_canonical_clean(tiny_repo["repo"])


@pytest.mark.parametrize("location", ["conftest.py", "tests/conftest.py"])
def test_agent_added_conftest_cannot_force_pass(tmp_path: Path, tiny_repo: dict[str, Path | str], location: str) -> None:
    repo = Path(tiny_repo["repo"])
    grader_paths = ["test_calc.py"]
    if location.startswith("tests/"):
        (repo / "tests").mkdir()
        (repo / "test_calc.py").rename(repo / "tests" / "test_calc.py")
        _run(["git", "add", "-A"], repo)
        _run(["git", "commit", "-m", "move test into tests directory"], repo)
        tiny_repo["base_commit"] = _run(["git", "rev-parse", "HEAD"], repo).stdout.strip()
        grader_paths = ["tests/test_calc.py"]
    agent = _agent(tmp_path, f"p = Path({location!r}); p.parent.mkdir(exist_ok=True); p.write_text('import pytest\\ndef pytest_runtest_setup(item):\\n    pytest.skip(\"forced\")\\n')")
    result, row = _run_forge(tmp_path, tiny_repo, agent, grader_paths=grader_paths)
    assert result.status == "failed"
    assert location in json.loads(row["protected_paths_modified"])
    _assert_canonical_clean(repo)


@pytest.mark.parametrize("name", ["pytest.ini", "tox.ini", "setup.cfg", "pyproject.toml"])
def test_agent_config_edit_cannot_change_grading(tmp_path: Path, tiny_repo: dict[str, Path | str], name: str) -> None:
    repo = Path(tiny_repo["repo"])
    (repo / name).write_text("[pytest]\naddopts = -q\n" if name != "pyproject.toml" else "[tool.pytest.ini_options]\naddopts = '-q'\n")
    _run(["git", "add", name], repo)
    _run(["git", "commit", "-m", "add pytest config"], repo)
    tiny_repo["base_commit"] = _run(["git", "rev-parse", "HEAD"], repo).stdout.strip()
    edited = "[tool.pytest.ini_options]\naddopts = '--ignore=test_calc.py'\n" if name == "pyproject.toml" else "[pytest]\naddopts = --ignore=test_calc.py\n"
    agent = _agent(tmp_path, f"Path({name!r}).write_text({edited!r})")
    result, row = _run_forge(tmp_path, tiny_repo, agent)
    assert result.status == "failed"
    assert name in json.loads(row["protected_paths_modified"])
    _assert_canonical_clean(repo)


def test_agent_added_shadow_test_is_removed(tmp_path: Path, tiny_repo: dict[str, Path | str]) -> None:
    agent = _agent(tmp_path, "Path('test_calc.py').rename('old_test.py')\nPath('tests').mkdir()\nPath('tests/test_calc.py').write_text('def test_fake(): assert True\\n')")
    result, row = _run_forge(tmp_path, tiny_repo, agent)
    assert result.status == "failed"
    assert "test_calc.py" in json.loads(row["protected_paths_modified"])
    assert "tests/test_calc.py" in json.loads(row["protected_paths_modified"])
    _assert_canonical_clean(tiny_repo["repo"])


@pytest.mark.parametrize("action", ["symlink", "directory"])
def test_protected_path_replacement_is_restored(tmp_path: Path, tiny_repo: dict[str, Path | str], action: str) -> None:
    repo = Path(tiny_repo["repo"])
    (repo / "tests").mkdir()
    (repo / "tests" / "test_calc.py").write_text((repo / "test_calc.py").read_text())
    (repo / "test_calc.py").unlink()
    _run(["git", "add", "-A"], repo)
    _run(["git", "commit", "-m", "move protected test"], repo)
    tiny_repo["base_commit"] = _run(["git", "rev-parse", "HEAD"], repo).stdout.strip()
    body = "Path('tests/test_calc.py').unlink(); Path('tests/test_calc.py').symlink_to('missing.py')" if action == "symlink" else "import shutil; shutil.rmtree('tests')"
    agent = _agent(tmp_path, body)
    result, row = _run_forge(tmp_path, tiny_repo, agent, grader_paths=["tests"])
    assert result.status == "failed"
    assert "tests" in json.loads(row["protected_paths_modified"])
    _assert_canonical_clean(repo)


def test_clone_does_not_change_canonical_git_objects_or_refs(tmp_path: Path, tiny_repo: dict[str, Path | str]) -> None:
    repo = Path(tiny_repo["repo"])
    before = _git_fingerprint(repo)
    agent = _agent(tmp_path, "import subprocess\nfor args in [['branch', 'agent-branch'], ['add', 'calc.py'], ['-c', 'user.name=Forge', '-c', 'user.email=forge@example.test', 'commit', '--allow-empty', '-m', 'agent'], ['update-ref', 'refs/heads/agent-ref', 'HEAD'], ['gc']]: subprocess.run(['git', *args], check=True, stdout=subprocess.DEVNULL)")
    result, _ = _run_forge(tmp_path, tiny_repo, agent)
    assert result.status == "failed"
    assert _git_fingerprint(repo) == before
    _assert_canonical_clean(repo)


def test_disposable_clone_is_removed(tmp_path: Path, tiny_repo: dict[str, Path | str], monkeypatch: pytest.MonkeyPatch) -> None:
    roots: list[Path] = []
    original = checkout_module.disposable_clone

    @contextmanager
    def tracked_clone(repo: Path, commit: str):
        with original(repo, commit) as clone:
            roots.append(clone.parent)
            yield clone

    monkeypatch.setattr(runner_module, "disposable_clone", tracked_clone)
    agent = _agent(tmp_path, "pass")
    result, _ = _run_forge(tmp_path, tiny_repo, agent)
    assert result.status == "failed"
    assert len(roots) == 1
    assert not roots[0].exists()
    _assert_canonical_clean(tiny_repo["repo"])


@pytest.mark.parametrize("sleep_s", [0, 5])
def test_agent_background_child_is_killed(tmp_path: Path, tiny_repo: dict[str, Path | str], sleep_s: int) -> None:
    marker = tmp_path / "child-survived"
    child_code = f"import time; from pathlib import Path; time.sleep(1); Path({str(marker)!r}).write_text('alive')"
    agent = _agent(tmp_path, f"import subprocess, time\nsubprocess.Popen([{sys.executable!r}, '-c', {child_code!r}])\ntime.sleep({sleep_s})")
    result, _ = _run_forge(tmp_path, tiny_repo, agent, agent_timeout_s=0.3 if sleep_s else 3)
    assert result.status == ("agent_timeout" if sleep_s else "failed")
    time.sleep(1.2)
    assert not marker.exists()
    _assert_canonical_clean(tiny_repo["repo"])


@pytest.mark.xfail(strict=True, reason="A child that creates a new session escapes POSIX process-group cleanup")
def test_agent_detached_child_is_killed(tmp_path: Path, tiny_repo: dict[str, Path | str]) -> None:
    marker = tmp_path / "detached-child-survived"
    child_code = f"import time; from pathlib import Path; time.sleep(1); Path({str(marker)!r}).write_text('alive')"
    agent = _agent(tmp_path, f"import subprocess\nsubprocess.Popen([{sys.executable!r}, '-c', {child_code!r}], start_new_session=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)")
    result, _ = _run_forge(tmp_path, tiny_repo, agent)
    assert result.status == "failed"
    time.sleep(1.2)
    assert not marker.exists()
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
    grader_paths: list[str] | None = None,
    trial: int = 1,
) -> tuple[object, sqlite3.Row]:
    before = _git_fingerprint(Path(tiny_repo["repo"]))
    clones_before = _clone_roots()
    task = _task_file(
        tmp_path,
        tiny_repo,
        base_commit=base_commit,
        agent_timeout_s=agent_timeout_s,
        grader_timeout_s=grader_timeout_s,
        grader_cmd=grader_cmd,
        grader_paths=grader_paths,
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
    assert _git_fingerprint(Path(tiny_repo["repo"])) == before
    assert _clone_roots() == clones_before
    return result, row


def _task_file(
    tmp_path: Path,
    tiny_repo: dict[str, Path | str],
    *,
    base_commit: str | None = None,
    agent_timeout_s: float = 3,
    grader_timeout_s: float = 3,
    grader_cmd: list[str] | None = None,
    grader_paths: list[str] | None = None,
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
            grader_paths = {grader_paths or ['test_calc.py']!r}
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


def _git_fingerprint(repo: Path) -> tuple[str, str, int]:
    refs = _run(["git", "for-each-ref", "--format=%(refname) %(objectname)"], repo).stdout
    head = _run(["git", "rev-parse", "HEAD"], repo).stdout
    objects = list((repo / ".git" / "objects").rglob("*"))
    return refs, head, len([path for path in objects if path.is_file()])


def _clone_roots() -> set[Path]:
    return set(Path(tempfile.gettempdir()).glob("forge-clone-*"))
