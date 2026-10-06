from __future__ import annotations

from contextlib import contextmanager
import hashlib
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


def test_committed_protected_tampering_is_restored_from_snapshot(tmp_path: Path, tiny_repo: dict[str, Path | str]) -> None:
    agent = _agent(
        tmp_path,
        "import subprocess\n"
        "Path('test_calc.py').write_text('def test_fake(): assert True\\n')\n"
        "subprocess.run(['git', 'add', 'test_calc.py'], check=True)\n"
        "subprocess.run(['git', '-c', 'user.name=Forge', '-c', 'user.email=forge@example.test', "
        "'commit', '-m', 'tamper'], check=True, capture_output=True)",
    )
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
    assert version == 4
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
    assert row["skill_id"] is None
    assert row["skill_sha256"] is None
    assert row["prompt_template_version"] is None
    assert row["final_prompt"] == "Fix add_one."
    assert row["final_prompt_sha256"] == hashlib.sha256(b"Fix add_one.").hexdigest()
    assert row["snapshot_tree_sha"] == _run(["git", "rev-parse", f"{tiny_repo['base_commit']}^{{tree}}"], Path(tiny_repo["repo"])).stdout.strip()
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


def test_baseline_prompt_is_byte_identical(tmp_path: Path, tiny_repo: dict[str, Path | str]) -> None:
    prompt = "  Fix add_one.\nKeep tests intact.  \n"
    agent = _agent(tmp_path, "import os, sys\nsys.stdout.buffer.write(os.environ['FORGE_AGENT_PROMPT'].encode('utf-8'))")
    result, row = _run_forge(tmp_path, tiny_repo, agent, agent_prompt=prompt)
    assert result.status == "failed"
    assert Path(row["stdout_path"]).read_bytes() == prompt.encode("utf-8")
    assert row["final_prompt"] == prompt
    assert row["final_prompt_sha256"] == hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    assert row["skill_id"] is None
    assert row["skill_sha256"] is None
    assert row["prompt_template_version"] is None


def test_skill_prompt_and_hashes_are_recorded(tmp_path: Path, tiny_repo: dict[str, Path | str]) -> None:
    skill = tmp_path / "SKILL.md"
    skill_bytes = b"First step: inspect the code.\nSecond step: test the fix.\n"
    skill.write_bytes(skill_bytes)
    prompt = "Fix add_one.\n"
    agent = _agent(tmp_path, "import os, sys\nsys.stdout.buffer.write(os.environ['FORGE_AGENT_PROMPT'].encode('utf-8'))")
    result, row = _run_forge(tmp_path, tiny_repo, agent, condition="skill", skill=skill, agent_prompt=prompt)
    expected = "Skill instructions:\n" + skill_bytes.decode() + "\n\nTask:\n" + prompt
    assert result.status == "failed"
    assert Path(row["stdout_path"]).read_bytes() == expected.encode("utf-8")
    assert row["skill_id"] == tmp_path.name
    assert row["skill_sha256"] == hashlib.sha256(skill_bytes).hexdigest()
    assert row["final_prompt_sha256"] == hashlib.sha256(expected.encode("utf-8")).hexdigest()
    assert row["final_prompt"] == expected
    assert row["prompt_template_version"] == 1
    assert row["snapshot_tree_sha"] == _run(["git", "rev-parse", f"{tiny_repo['base_commit']}^{{tree}}"], Path(tiny_repo["repo"])).stdout.strip()
    skill.write_text("The skill file changed after this run.\n")
    with sqlite3.connect(tmp_path / "runs.sqlite") as conn:
        stored_prompt = conn.execute("SELECT final_prompt FROM runs WHERE run_id = ?", (result.run_id,)).fetchone()[0]
    assert stored_prompt == expected


def test_skill_ids_come_from_distinct_parent_directories(tmp_path: Path, tiny_repo: dict[str, Path | str]) -> None:
    agent = _agent(tmp_path, "pass")
    db = tmp_path / "skill-ids.sqlite"
    ids = []
    for name in ("foo", "bar"):
        skill = tmp_path / "skills" / name / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text(f"Use the {name} approach.\n")
        result, row = _run_forge(tmp_path, tiny_repo, agent, db=db, condition="skill", skill=skill)
        assert result.status == "failed"
        ids.append(row["skill_id"])
    assert ids == ["foo", "bar"]
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 2


def test_non_standard_skill_filename_uses_stem(tmp_path: Path, tiny_repo: dict[str, Path | str]) -> None:
    skill = tmp_path / "review-guide.md"
    skill.write_text("Review the code first.\n")
    agent = _agent(tmp_path, "pass")
    result, row = _run_forge(tmp_path, tiny_repo, agent, condition="skill", skill=skill)
    assert result.status == "failed"
    assert row["skill_id"] == "review-guide"


@pytest.mark.parametrize("value", ["", "  \t  "])
def test_empty_or_whitespace_skill_id_is_invalid_config(tmp_path: Path, tiny_repo: dict[str, Path | str], value: str) -> None:
    skill = tmp_path / "SKILL.md"
    skill.write_text("Inspect first.\n")
    agent = _agent(tmp_path, "pass")
    result, row = _run_forge(tmp_path, tiny_repo, agent, condition="skill", skill=skill, skill_id=value)
    assert result.status == "invalid_config"
    assert row["skill_id"] is None
    assert row["agent_exit_code"] is None


def test_baseline_skill_id_option_is_invalid_and_null(tmp_path: Path, tiny_repo: dict[str, Path | str]) -> None:
    agent = _agent(tmp_path, "pass")
    result, row = _run_forge(tmp_path, tiny_repo, agent, skill_id="foo")
    assert result.status == "invalid_config"
    assert row["skill_id"] is None


@pytest.mark.parametrize("content", [None, b"\xff"])
def test_missing_or_non_utf8_skill_is_invalid_config(tmp_path: Path, tiny_repo: dict[str, Path | str], content: bytes | None) -> None:
    skill = tmp_path / "SKILL.md"
    if content is not None:
        skill.write_bytes(content)
    agent = _agent(tmp_path, "pass")
    result, row = _run_forge(tmp_path, tiny_repo, agent, condition="skill", skill=skill)
    assert result.status == "invalid_config"
    assert row["agent_exit_code"] is None
    assert row["final_prompt"] is None
    assert row["snapshot_tree_sha"] is None


@pytest.mark.parametrize("condition,provide_skill", [("baseline", True), ("skill", False)])
def test_condition_skill_mismatch_is_invalid_config(tmp_path: Path, tiny_repo: dict[str, Path | str], condition: str, provide_skill: bool) -> None:
    skill = tmp_path / "SKILL.md"
    skill.write_text("Follow the tests.\n")
    agent = _agent(tmp_path, "pass")
    result, row = _run_forge(tmp_path, tiny_repo, agent, condition=condition, skill=skill if provide_skill else None)
    assert result.status == "invalid_config"
    assert row["status"] == "invalid_config"
    assert row["agent_exit_code"] is None
    assert row["snapshot_tree_sha"] is None


def test_conditions_share_repo_environment_and_limits(tmp_path: Path, tiny_repo: dict[str, Path | str], monkeypatch: pytest.MonkeyPatch) -> None:
    skill = tmp_path / "SKILL.md"
    skill.write_text("Inspect first.\n")
    agent = _agent(tmp_path, "import json, os, subprocess\nprint(json.dumps({'tree': subprocess.check_output(['git', 'rev-parse', 'HEAD^{tree}'], text=True).strip(), 'status': subprocess.check_output(['git', 'status', '--porcelain'], text=True).strip(), 'env': dict(os.environ)}, sort_keys=True))")
    timeouts: list[float] = []
    original = runner_module.run_command

    def observed_run(*args, **kwargs):
        timeouts.append(args[2])
        return original(*args, **kwargs)

    monkeypatch.setattr(runner_module, "run_command", observed_run)
    _, baseline_row = _run_forge(tmp_path, tiny_repo, agent)
    _, skill_row = _run_forge(tmp_path, tiny_repo, agent, condition="skill", skill=skill)
    baseline = json.loads(Path(baseline_row["stdout_path"]).read_text())
    skilled = json.loads(Path(skill_row["stdout_path"]).read_text())
    assert baseline["tree"] == skilled["tree"] == baseline_row["snapshot_tree_sha"] == skill_row["snapshot_tree_sha"]
    assert baseline["status"] == skilled["status"] == ""
    assert baseline["env"].keys() == skilled["env"].keys()
    assert Path(baseline["env"].pop("HOME")).name == Path(skilled["env"].pop("HOME")).name == "agent-home"
    assert baseline["env"].pop("FORGE_AGENT_PROMPT") != skilled["env"].pop("FORGE_AGENT_PROMPT")
    assert baseline["env"] == skilled["env"]
    assert timeouts[:2] == timeouts[2:] == [3, 3]


def test_skill_text_never_enters_run_repository(tmp_path: Path, tiny_repo: dict[str, Path | str]) -> None:
    marker = "SECRET_SKILL_TEXT_827d"
    skill = tmp_path / "SKILL.md"
    skill.write_text(marker)
    agent = _agent(tmp_path, f"import os\nneedle = {marker!r}.encode()\nprint(any(needle in p.read_bytes() for p in Path('.').rglob('*') if p.is_file()))")
    result, row = _run_forge(tmp_path, tiny_repo, agent, condition="skill", skill=skill)
    assert result.status == "failed"
    assert Path(row["stdout_path"]).read_text().strip() == "False"


def test_cli_skill_option_and_condition_validation(tmp_path: Path, tiny_repo: dict[str, Path | str]) -> None:
    agent = _agent(tmp_path, "pass")
    task = _task_file(tmp_path, tiny_repo)
    skill = tmp_path / "SKILL.md"
    skill.write_text("Inspect the tests.\n")
    db = tmp_path / "cli-conditions.sqlite"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")

    def invoke(condition: str, with_skill: bool, skill_id: str | None = None) -> str:
        command = [
            sys.executable, "-m", "forge.cli", "run-once", str(task),
            "--condition", condition, "--trial", "1", "--seed", "123",
            "--experiment-id", "conditions", "--db", str(db),
        ]
        if with_skill:
            command += ["--skill", str(skill)]
        if skill_id is not None:
            command += ["--skill-id", skill_id]
        command += ["--agent-cmd", sys.executable, str(agent)]
        result = subprocess.run(command, cwd=tmp_path, env=env, capture_output=True, text=True, check=True)
        return result.stdout.strip().split()[1]

    assert invoke("skill", True, "explicit-foo") == "failed"
    assert invoke("baseline", True) == "invalid_config"
    assert invoke("skill", False) == "invalid_config"
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 3
        assert conn.execute("SELECT skill_id FROM runs WHERE condition = 'skill' AND status = 'failed'").fetchone()[0] == "explicit-foo"


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


def test_new_test_inside_protected_directory_is_removed(tmp_path: Path, tiny_repo: dict[str, Path | str]) -> None:
    repo = Path(tiny_repo["repo"])
    (repo / "tests").mkdir()
    (repo / "tests" / "test_calc.py").write_text((repo / "test_calc.py").read_text())
    (repo / "test_calc.py").unlink()
    _run(["git", "add", "-A"], repo)
    _run(["git", "commit", "-m", "move grader into protected directory"], repo)
    tiny_repo["base_commit"] = _run(["git", "rev-parse", "HEAD"], repo).stdout.strip()
    agent = _agent(tmp_path, "Path('tests/test_fake.py').write_text('def test_fake(): assert True\\n')")
    grader = [sys.executable, "-c", "from pathlib import Path; raise SystemExit(0 if Path('tests/test_fake.py').exists() else 1)"]
    result, row = _run_forge(tmp_path, tiny_repo, agent, grader_cmd=grader, grader_paths=["tests"])
    assert result.status == "failed"
    assert json.loads(row["protected_paths_modified"]) == ["tests"]
    _assert_canonical_clean(repo)


@pytest.mark.parametrize("name", ["sitecustomize.py", "usercustomize.py", "unittest.py", "json.py"])
def test_unittest_grader_rejects_import_shadows(tmp_path: Path, tiny_repo: dict[str, Path | str], name: str) -> None:
    repo = Path(tiny_repo["repo"])
    (repo / "test_calc.py").write_text(
        "import unittest\nfrom calc import add_one\n\nclass TestCalc(unittest.TestCase):\n"
        "    def test_add_one(self):\n        self.assertEqual(add_one(1), 2)\n",
        encoding="utf-8",
    )
    _run(["git", "add", "test_calc.py"], repo)
    _run(["git", "commit", "-m", "use unittest grader"], repo)
    tiny_repo["base_commit"] = _run(["git", "rev-parse", "HEAD"], repo).stdout.strip()
    agent = _agent(tmp_path, f"Path({name!r}).write_text('raise SystemExit(0)\\n')")
    result, row = _run_forge(
        tmp_path, tiny_repo, agent,
        grader_cmd=[sys.executable, "-m", "unittest", "discover"],
    )
    assert result.status == "failed"
    assert name in json.loads(row["protected_paths_modified"])
    _assert_canonical_clean(repo)


def test_snapshot_hides_later_history_and_objects(tmp_path: Path, tiny_repo: dict[str, Path | str]) -> None:
    repo = Path(tiny_repo["repo"])
    secret = "REFERENCE_FIX_ONLY_IN_LATER_COMMIT_9f4c"
    (repo / "calc.py").write_text(f"def add_one(value):\n    return value + 1  # {secret}\n")
    _run(["git", "add", "calc.py"], repo)
    _run(["git", "commit", "-m", "reference fix"], repo)
    later_commit = _run(["git", "rev-parse", "HEAD"], repo).stdout.strip()
    agent = _agent(
        tmp_path,
        "import subprocess\n"
        "for args in [['log', '--all', '--oneline'], ['rev-list', '--all'], ['reflog', '--all'], "
        "['fsck', '--lost-found', '--unreachable']]:\n"
        "    result = subprocess.run(['git', *args], capture_output=True, text=True)\n"
        "    print('COMMAND', args, result.stdout, result.stderr)\n"
        "data = b''.join(p.read_bytes() for p in Path('.git').rglob('*') if p.is_file())\n"
        f"print('FIX_IN_GIT_DIR', {secret!r}.encode() in data)\n"
        f"print('LATER_HASH_IN_GIT_DIR', {later_commit!r}.encode() in data)",
    )
    result, row = _run_forge(tmp_path, tiny_repo, agent)
    output = Path(row["stdout_path"]).read_text()
    assert result.status == "failed"
    assert secret not in output
    assert later_commit not in output
    assert "FIX_IN_GIT_DIR False" in output
    assert "LATER_HASH_IN_GIT_DIR False" in output
    _assert_canonical_clean(repo)


def test_snapshot_has_one_commit_no_remote_and_usable_git(tmp_path: Path, tiny_repo: dict[str, Path | str]) -> None:
    repo = Path(tiny_repo["repo"])
    expected_tree = _run(["git", "rev-parse", f"{tiny_repo['base_commit']}^{{tree}}"], repo).stdout.strip()
    (repo / "calc.py").write_text("def add_one(value):\n    return value + 1\n")
    _run(["git", "add", "calc.py"], repo)
    _run(["git", "commit", "-m", "later reference fix"], repo)
    agent = _agent(
        tmp_path,
        "import subprocess\n"
        "print('COMMIT_COUNT', len(subprocess.check_output(['git', 'rev-list', '--all']).splitlines()))\n"
        "print('TREE', subprocess.check_output(['git', 'rev-parse', 'HEAD^{tree}'], text=True).strip())\n"
        "for args in [['remote'], ['status', '--porcelain']]:\n"
        "    print('RESULT', args, subprocess.check_output(['git', *args], text=True).strip())\n"
        "Path('calc.py').write_text('def add_one(value):\\n    return value + 1\\n')\n"
        "print('DIFF', subprocess.check_output(['git', 'diff', '--', 'calc.py'], text=True))\n"
        "subprocess.run(['git', '-c', 'user.name=Forge', '-c', 'user.email=forge@example.test', "
        "'commit', '-am', 'agent change'], check=True, capture_output=True)",
    )
    result, row = _run_forge(tmp_path, tiny_repo, agent)
    output = Path(row["stdout_path"]).read_text()
    assert result.status == "passed"
    assert "RESULT ['remote'] \n" in output
    assert "DIFF diff --git" in output
    assert "COMMIT_COUNT 1\n" in output
    assert f"TREE {expected_tree}\n" in output
    assert row["agent_exit_code"] == 0
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


def test_snapshot_does_not_change_canonical_git_objects_or_refs(tmp_path: Path, tiny_repo: dict[str, Path | str]) -> None:
    repo = Path(tiny_repo["repo"])
    before = _git_fingerprint(repo)
    agent = _agent(tmp_path, "import subprocess\nfor args in [['branch', 'agent-branch'], ['add', 'calc.py'], ['-c', 'user.name=Forge', '-c', 'user.email=forge@example.test', 'commit', '--allow-empty', '-m', 'agent'], ['update-ref', 'refs/heads/agent-ref', 'HEAD'], ['gc']]: subprocess.run(['git', *args], check=True, stdout=subprocess.DEVNULL)")
    result, _ = _run_forge(tmp_path, tiny_repo, agent)
    assert result.status == "failed"
    assert _git_fingerprint(repo) == before
    _assert_canonical_clean(repo)


def test_disposable_snapshot_is_removed(tmp_path: Path, tiny_repo: dict[str, Path | str], monkeypatch: pytest.MonkeyPatch) -> None:
    roots: list[Path] = []
    original = checkout_module.disposable_snapshot

    @contextmanager
    def tracked_clone(repo: Path, commit: str):
        with original(repo, commit) as (checkout, snapshot_commit, tree):
            roots.append(checkout.parent)
            yield checkout, snapshot_commit, tree

    monkeypatch.setattr(runner_module, "disposable_snapshot", tracked_clone)
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
    condition: str = "baseline",
    skill: Path | None = None,
    skill_id: str | None = None,
    agent_prompt: str = "Fix add_one.",
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
        agent_prompt=agent_prompt,
    )
    db_path = db or (tmp_path / "runs.sqlite")
    result = run_once(
        RunOnceRequest(
            task_path=task,
            condition=condition,
            trial=trial,
            seed=99,
            experiment_id="exp",
            db_path=db_path,
            agent_cmd=[sys.executable, str(agent)],
            **({"skill_path": skill} if skill is not None else {}),
            **({"skill_id": skill_id} if skill_id is not None else {}),
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
    agent_prompt: str = "Fix add_one.",
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
            agent_prompt = {json.dumps(agent_prompt)}
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
    return set(Path(tempfile.gettempdir()).glob("forge-snapshot-*"))


def _codex_stub(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "codex-stub"
    path.write_text(
        f"#!{sys.executable}\n"
        "import json, os, pathlib, sys, time\n"
        "from pathlib import Path\n"
        "if sys.argv[1:] == ['--version']:\n"
        "    print('codex-cli 0.test')\n"
        "    raise SystemExit(0)\n"
        + body + "\n",
        encoding="utf-8",
    )
    path.chmod(0o755)
    return path


def _run_codex(tmp_path: Path, tiny_repo: dict[str, Path | str], stub: Path, auth: Path, **kwargs):
    task = _task_file(tmp_path, tiny_repo, agent_timeout_s=kwargs.pop("timeout", 3))
    db = tmp_path / "codex.sqlite"
    result = run_once(RunOnceRequest(
        task_path=task, condition=kwargs.pop("condition", "baseline"), trial=1,
        seed=99, experiment_id="codex", db_path=db, agent_cmd=[], agent="codex",
        model="gpt-test", reasoning_effort="low", codex_bin=str(stub),
        codex_auth=auth, **kwargs,
    ))
    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (result.run_id,)).fetchone()
    return result, row, db


def test_codex_stub_telemetry_and_clean_home(tmp_path: Path, tiny_repo: dict[str, Path | str]) -> None:
    auth = tmp_path / "auth.json"
    auth.write_text('{"token":"sentinel-auth-value-1234567890"}')
    stub = _codex_stub(tmp_path,
        "home = Path(os.environ['CODEX_HOME'])\n"
        "assert home.stat().st_mode & 0o777 == 0o700\n"
        "assert [p.name for p in home.iterdir()] == ['auth.json']\n"
        "assert (home / 'auth.json').stat().st_mode & 0o777 == 0o600\n"
        "assert json.loads((home / 'auth.json').read_text())['token'] == 'sentinel-auth-value-1234567890'\n"
        "assert 'FORGE_AGENT_PROMPT' not in os.environ\n"
        f"assert os.environ['HOME'] != {str(Path.home())!r}\n"
        f"assert {str(auth)!r} not in os.environ.values()\n"
        "assert sys.argv[1:8] == ['exec', '--json', '--sandbox', 'workspace-write', '-m', 'gpt-test', '-c']\n"
        "assert sys.argv[8] == 'model_reasoning_effort=low'\n"
        "prompt = sys.stdin.read() if sys.argv[9:] == ['-'] else sys.argv[9]\n"
        "assert prompt == 'Fix add_one.'\n"
        "Path(os.environ['HOME']).joinpath('codex-home-path').write_text(str(home))\n"
        "print(json.dumps({'type':'thread.started'}))\n"
        "print(json.dumps({'type':'turn.started'}))\n"
        "print(json.dumps({'type':'item.completed','item':{'type':'command_execution'}}))\n"
        "print(json.dumps({'type':'item.completed','item':{'type':'file_change'}}))\n"
        "print(json.dumps({'type':'turn.completed','usage':{'input_tokens':100,'cached_input_tokens':20,'output_tokens':30}}))")
    result, row, _ = _run_codex(tmp_path, tiny_repo, stub, auth)
    assert result.status == "failed"
    assert (row["agent_name"], row["agent_version"], row["model"], row["reasoning_effort"]) == ("codex", "codex-cli 0.test", "gpt-test", "low")
    assert (row["input_tokens"], row["cached_input_tokens"], row["output_tokens"]) == (100, 20, 30)
    assert (row["command_count"], row["file_change_count"], row["telemetry_status"]) == (1, 1, "ok")
    assert row["wall_seconds"] >= 0
    assert not Path((Path(row["stdout_path"]).parent / "agent-home" / "codex-home-path").read_text()).exists()
    assert row["secret_exposure"] == 0


@pytest.mark.parametrize("body,expected", [("pass", "missing"), ("print('{bad')", "unparseable")])
def test_codex_missing_or_bad_telemetry_is_nullable(tmp_path: Path, tiny_repo: dict[str, Path | str], body: str, expected: str) -> None:
    auth = tmp_path / "auth.json"
    auth.write_text('{"token":"sentinel-auth-value-1234567890"}')
    stub = _codex_stub(tmp_path, body)
    result, row, _ = _run_codex(tmp_path, tiny_repo, stub, auth)
    assert result.status == "failed"
    assert row["telemetry_status"] == expected
    assert all(row[name] is None for name in ("input_tokens", "cached_input_tokens", "output_tokens", "command_count", "file_change_count"))


def test_codex_exact_secret_detection_and_cleanup(tmp_path: Path, tiny_repo: dict[str, Path | str]) -> None:
    sentinel = "sentinel-auth-value-1234567890"
    auth = tmp_path / "auth.json"
    auth.write_text(json.dumps({"token": sentinel}))
    stub = _codex_stub(tmp_path,
        "secret = json.loads(Path(os.environ['CODEX_HOME']).joinpath('auth.json').read_text())['token']\n"
        "Path('leaked.txt').write_text(secret)\n"
        "print(secret)\n"
        "print(secret, file=sys.stderr)\n"
        "print(json.dumps({'type':'turn.completed','usage':{'input_tokens':1,'cached_input_tokens':0,'output_tokens':1}}))")
    result, row, db = _run_codex(tmp_path, tiny_repo, stub, auth)
    assert result.status == "failed"
    assert row["secret_exposure"] == 1
    assert "[REDACTED]" in Path(row["stdout_path"]).read_text()
    assert sentinel not in Path(row["stdout_path"]).read_text()
    assert "[REDACTED]" in Path(row["stderr_path"]).read_text()
    assert sentinel not in Path(row["stderr_path"]).read_text()
    assert sentinel.encode() not in db.read_bytes()


@pytest.mark.parametrize("body,timeout,status", [("pass", 3, "failed"), ("time.sleep(5)", 0.2, "agent_timeout"), ("raise RuntimeError('crash')", 3, "agent_error")])
def test_codex_home_removed_all_exits(tmp_path: Path, tiny_repo: dict[str, Path | str], body: str, timeout: float, status: str) -> None:
    auth = tmp_path / "auth.json"
    auth.write_text('{"token":"sentinel-auth-value-1234567890"}')
    stub = _codex_stub(tmp_path, "Path(os.environ['HOME']).joinpath('codex-home-path').write_text(os.environ['CODEX_HOME'])\n" + body)
    result, row, _ = _run_codex(tmp_path, tiny_repo, stub, auth, timeout=timeout)
    assert result.status == status
    home_path = Path(row["stdout_path"]).parent / "agent-home" / "codex-home-path"
    assert home_path.exists()
    assert not Path(home_path.read_text()).exists()


def test_codex_conditions_change_only_stdin_prompt(tmp_path: Path, tiny_repo: dict[str, Path | str]) -> None:
    auth = tmp_path / "auth.json"
    auth.write_text('{"token":"sentinel-auth-value-1234567890"}')
    skill = tmp_path / "skills" / "foo" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("Inspect the source first.\n")
    stub = _codex_stub(tmp_path,
        "home = Path(os.environ['CODEX_HOME'])\n"
        "prompt = sys.stdin.read()\n"
        "capture = {'argv':sys.argv[1:], 'env_keys':sorted(os.environ), 'auth':(home/'auth.json').read_text(), 'prompt':prompt}\n"
        "Path(os.environ['HOME']).joinpath('capture.json').write_text(json.dumps(capture))\n"
        "print(json.dumps({'type':'turn.completed','usage':{'input_tokens':2,'cached_input_tokens':0,'output_tokens':1}}))")
    _, base_row, _ = _run_codex(tmp_path, tiny_repo, stub, auth)
    _, skill_row, _ = _run_codex(tmp_path, tiny_repo, stub, auth, condition="skill", skill_path=skill)
    base = json.loads((Path(base_row["stdout_path"]).parent / "agent-home" / "capture.json").read_text())
    skilled = json.loads((Path(skill_row["stdout_path"]).parent / "agent-home" / "capture.json").read_text())
    assert base["argv"] == skilled["argv"]
    assert base["env_keys"] == skilled["env_keys"]
    assert base["auth"] == skilled["auth"] == auth.read_text()
    assert base["prompt"] == "Fix add_one."
    assert skilled["prompt"] == "Skill instructions:\nInspect the source first.\n\n\nTask:\nFix add_one."
    assert base_row["agent_cmd"] == skill_row["agent_cmd"]


def test_codex_missing_binary_cleans_home(tmp_path: Path, tiny_repo: dict[str, Path | str], monkeypatch: pytest.MonkeyPatch) -> None:
    auth = tmp_path / "auth.json"
    auth.write_text('{"token":"sentinel-auth-value-1234567890"}')
    homes: list[Path] = []
    original = runner_module.isolated_auth

    @contextmanager
    def observed_auth(source: Path):
        with original(source) as (home, secrets):
            homes.append(home)
            yield home, secrets

    monkeypatch.setattr(runner_module, "isolated_auth", observed_auth)
    result, row, _ = _run_codex(tmp_path, tiny_repo, tmp_path / "missing-codex", auth)
    assert result.status == "infra_error"
    assert row["telemetry_status"] is None
    assert len(homes) == 1 and not homes[0].exists()


def test_cli_codex_mode_and_required_options(tmp_path: Path, tiny_repo: dict[str, Path | str]) -> None:
    auth = tmp_path / "auth.json"
    auth.write_text('{"token":"sentinel-auth-value-1234567890"}')
    stub = _codex_stub(tmp_path, "print(json.dumps({'type':'turn.completed','usage':{'input_tokens':4,'cached_input_tokens':1,'output_tokens':2}}))")
    task = _task_file(tmp_path, tiny_repo)
    db = tmp_path / "cli-codex.sqlite"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    common = [
        sys.executable, "-m", "forge.cli", "run-once", str(task),
        "--condition", "baseline", "--trial", "1", "--seed", "1",
        "--experiment-id", "cli-codex", "--db", str(db),
        "--agent", "codex", "--codex-bin", str(stub), "--codex-auth", str(auth),
    ]
    missing = subprocess.run(common, env=env, cwd=tmp_path, capture_output=True, text=True, check=True)
    assert missing.stdout.strip().endswith("invalid_config")
    working = subprocess.run(common + ["--model", "gpt-test", "--reasoning-effort", "low"], env=env, cwd=tmp_path, capture_output=True, text=True, check=True)
    assert working.stdout.strip().endswith("failed")
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT input_tokens FROM runs WHERE status='failed'").fetchone()[0] == 4
