from __future__ import annotations

from collections import Counter
import hashlib
import importlib.util
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
import tomllib

import pytest

from forge.experiment import load_manifest
from forge.checkout import disposable_snapshot
from forge.process import ProcessResult
from forge.runner import _grade
from forge.scheduler import planned_runs, run_experiment
from forge.task import load_task


ROOT = Path(__file__).resolve().parents[1] / "benchmarks" / "final"
SKILL = Path(__file__).resolve().parents[1] / "skills/systematic-debugging/v2/SKILL.md"
FAMILIES = {"input-validation", "state-mutation", "algorithm-logic", "integration-boundary", "error-edge"}


def _load_script(name):
    spec = importlib.util.spec_from_file_location(f"final_{name}", ROOT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


@pytest.fixture(scope="module")
def prepared(tmp_path_factory):
    root = tmp_path_factory.mktemp("final-benchmark") / "final"
    shutil.copytree(ROOT / "cases", root / "cases")
    shutil.copytree(ROOT / "smoke_cases", root / "smoke_cases")
    shutil.copy2(ROOT / "manifest.template.toml", root / "manifest.template.toml")
    shutil.copy2(ROOT / "smoke.template.toml", root / "smoke.template.toml")
    manifest = _load_script("prepare").prepare_final(root, model="gpt-5.6-sol", skill_path=SKILL)
    return root, manifest


def test_final_metadata_and_independence(prepared):
    root, manifest_path = prepared
    manifest = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["phase"] == "final"
    assert manifest["conditions"] == ["baseline", "skill"]
    assert manifest["trials_per_condition"] == 5
    assert manifest["model"] == "gpt-5.6-sol"
    assert manifest["reasoning_effort"] == "medium"
    assert manifest["max_total_tokens"] == 45_000_000
    assert len(manifest["tasks"]) == 15
    assert hashlib.sha256(SKILL.read_bytes()).hexdigest() == "a08970b2b2b04a09924097f31537899d1631d289d333408f889407b03a58676e"
    metadata = [tomllib.loads(path.read_text()) for path in sorted((root / "cases").glob("*/case.toml"))]
    assert Counter(item["family"] for item in metadata) == {family: 3 for family in FAMILIES}
    assert len({item["task_id"] for item in metadata}) == 15
    smoke = tomllib.loads((root / "generated/smoke.toml").read_text())
    assert len(smoke["tasks"]) == 3
    assert set(smoke["tasks"]).isdisjoint(manifest["tasks"])


def test_freeze_input_package_matches_materialized_manifest(prepared):
    root, manifest_path = prepared
    import json

    package = json.loads((ROOT / "FREEZE_INPUTS.json").read_text())
    manifest = load_manifest(manifest_path)
    assert package["skill"]["sha256"] == manifest.skill_sha256
    assert package["benchmark"]["version"] == "final-v1"
    assert package["manifest"]["planned_observations"] == len(planned_runs(manifest)) == 150
    expected = {
        task["task_id"]: (task["base_commit"], task["reference_commit"])
        for task in package["tasks"]
    }
    actual = {}
    for path in sorted((root / "generated/tasks/final").glob("*.toml")):
        data = tomllib.loads(path.read_text())
        actual[data["task_id"]] = (data["base_commit"], data["reference_commit"])
    assert actual == expected


def test_all_tasks_validate_and_hide_references(prepared):
    root, _ = prepared
    _load_script("validate").validate_final(root)
    for database, expected in (("final.sqlite", 15), ("final-smoke.sqlite", 3)):
        with sqlite3.connect(root / "generated" / database) as conn:
            rows = conn.execute(
                "SELECT repeats, base_fails, reference_passes, protected_diff_empty, deterministic, reference_hidden, overall_ok FROM task_validations"
            ).fetchall()
        assert len(rows) == expected
        assert all(row == (3, 1, 1, 1, 1, 1, 1) for row in rows)


def test_materialization_is_reproducible(prepared, tmp_path):
    root, _ = prepared
    second = tmp_path / "final"
    shutil.copytree(ROOT / "cases", second / "cases")
    shutil.copytree(ROOT / "smoke_cases", second / "smoke_cases")
    shutil.copy2(ROOT / "manifest.template.toml", second / "manifest.template.toml")
    shutil.copy2(ROOT / "smoke.template.toml", second / "smoke.template.toml")
    _load_script("prepare").prepare_final(second, model="gpt-5.6-sol", skill_path=SKILL)
    for first in sorted((root / "generated/tasks").glob("*/*.toml")):
        relative = first.relative_to(root / "generated/tasks")
        left = tomllib.loads(first.read_text())
        right = tomllib.loads((second / "generated/tasks" / relative).read_text())
        assert (left["base_commit"], left["reference_commit"]) == (right["base_commit"], right["reference_commit"])


def test_plans_are_150_final_and_6_smoke_without_agents(prepared, monkeypatch, capsys):
    root, final_path = prepared
    monkeypatch.setattr("forge.experiment.codex_version", lambda *_args: "codex-stub")
    monkeypatch.setattr("forge.scheduler.run_once", lambda *_args, **_kwargs: pytest.fail("plan launched an agent"))
    final = load_manifest(final_path)
    smoke = load_manifest(root / "generated/smoke.toml")
    final_plan = planned_runs(final)
    smoke_plan = planned_runs(smoke)
    assert len(final_plan) == 150
    assert Counter(condition for _, condition, *_ in final_plan) == {"baseline": 75, "skill": 75}
    assert len(smoke_plan) == 6
    assert Counter(condition for _, condition, *_ in smoke_plan) == {"baseline": 3, "skill": 3}
    capsys.readouterr()
    run_experiment(smoke, plan_only=True)
    assert len(capsys.readouterr().out.splitlines()) == 6
    with sqlite3.connect(smoke.db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0


def test_task_commits_and_protected_graders(prepared):
    root, _ = prepared
    for path in sorted((root / "generated/tasks").glob("*/*.toml")):
        task = load_task(path, validate_reference=True)
        assert task.version in {"final-v1", "final-smoke-v1"}
        assert task.grader_paths == ["tests"]
        assert task.base_commit != task.reference_commit
        assert _git(task.repo_path, "diff", "--name-only", task.base_commit, task.reference_commit).splitlines() == [
            name for name in _git(task.repo_path, "diff", "--name-only", task.base_commit, task.reference_commit).splitlines()
            if not name.startswith("tests/")
        ]


def test_protected_graders_survive_adversarial_files(prepared):
    root, _ = prepared
    for path in sorted((root / "generated/tasks").glob("*/*.toml")):
        task = load_task(path, validate_reference=True)
        with disposable_snapshot(task.repo_path, task.reference_commit) as (checkout, snapshot_commit, _):
            shutil.rmtree(checkout / "tests")
            (checkout / "tests").mkdir()
            (checkout / "tests/test_behavior.py").write_text("raise SystemExit('tampered')\n")
            (checkout / "tests/test_shadow.py").write_text("def test_fake(): return True\n")
            (checkout / "sitecustomize.py").write_text("raise SystemExit('startup tampered')\n")
            (checkout / "unittest.py").write_text("raise SystemExit('shadowed')\n")
            with tempfile.TemporaryDirectory() as log_root:
                logs = Path(log_root)
                dummy = ProcessResult(0, False, logs / "unused.out", logs / "unused.err")
                changed, _, status = _grade(checkout, snapshot_commit, task, logs, dummy)
            assert status == "passed", task.task_id
            assert "tests" in changed
            assert "sitecustomize.py" in changed
            assert "unittest.py" in changed
