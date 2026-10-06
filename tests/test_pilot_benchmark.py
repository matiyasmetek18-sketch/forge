from __future__ import annotations

from collections import Counter
import hashlib
import importlib.util
from pathlib import Path
import shutil
import sqlite3
import subprocess

import pytest

from forge.experiment import load_manifest
from forge.scheduler import planned_runs, run_experiment
from forge.task import load_task


ROOT = Path(__file__).resolve().parents[1] / "benchmarks" / "pilot"
FAMILIES = {"input-validation", "state-mutation", "algorithm-logic", "integration-boundary", "error-edge"}


@pytest.fixture(scope="module")
def prepared(tmp_path_factory):
    module = _load_script("prepare")
    root = tmp_path_factory.mktemp("pilot") / "pilot"
    shutil.copytree(ROOT / "cases", root / "cases")
    shutil.copy2(ROOT / "manifest.template.toml", root / "manifest.template.toml")
    shutil.copy2(ROOT / "smoke.template.toml", root / "smoke.template.toml")
    manifest = module.prepare_pilot(root, model="test-model", skill_path=Path(__file__).resolve().parents[1] / "skills/systematic-debugging/v1/SKILL.md")
    return root, manifest


def _load_script(name):
    spec = importlib.util.spec_from_file_location(f"pilot_{name}", ROOT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def _repo_state(repo: Path):
    return (
        _git(repo, "rev-parse", "HEAD"),
        _git(repo, "for-each-ref", "--format=%(refname) %(objectname)"),
        _git(repo, "count-objects", "-v"),
        _git(repo, "status", "--porcelain"),
    )


@pytest.fixture(scope="module")
def validated(prepared):
    root, manifest = prepared
    paths = sorted((root / "generated" / "tasks").glob("*.toml"))
    before = {path: _repo_state(load_task(path).repo_path) for path in paths}
    _load_script("validate").validate_pilot(root)
    after = {path: _repo_state(load_task(path).repo_path) for path in paths}
    return root, manifest, before, after


def test_pilot_configs_and_metadata(prepared):
    root, manifest_path = prepared
    import tomllib

    manifest_data = tomllib.loads(manifest_path.read_text())
    assert manifest_data["phase"] == "pilot"
    assert manifest_data["agent"] == "codex"
    assert manifest_data["conditions"] == ["baseline", "skill"]
    assert manifest_data["trials_per_condition"] == 3
    assert manifest_data["max_total_runs"] >= 60
    assert manifest_data["max_total_tokens"] > 0
    assert len(manifest_data["tasks"]) == 10
    assert hashlib.sha256(Path(manifest_data["skill"]).read_bytes()).hexdigest() == "95437cbf0e659d93999fd58863210099ef7fc122b6803005d23757fc4e37ec6d"
    ids = []
    families = Counter()
    for path in sorted((root / "cases").glob("*/case.toml")):
        metadata = tomllib.loads(path.read_text())
        assert metadata["phase"] == "pilot"
        assert metadata["family"] in FAMILIES
        assert metadata["requires_network"] is False
        families[metadata["family"]] += 1
        ids.append(metadata["task_id"])
        task = load_task(root / "generated" / "tasks" / f"{metadata['task_id']}.toml", validate_reference=True)
        assert task.task_id == metadata["task_id"]
        assert task.base_commit != task.reference_commit
        assert task.grader_paths == ["tests"]
        assert _git(task.repo_path, "rev-parse", task.base_commit)
        assert _git(task.repo_path, "rev-parse", task.reference_commit)
        assert "SKILL.md" not in _git(task.repo_path, "ls-tree", "-r", "--name-only", task.base_commit)
    assert len(ids) == len(set(ids)) == 10
    assert families == {name: 2 for name in FAMILIES}


def test_all_pilot_graders_and_canonical_repos_unchanged(validated):
    root, _, before, after = validated
    assert after == before
    db = root / "generated" / "pilot.sqlite"
    with sqlite3.connect(db) as conn:
        rows = conn.execute("SELECT repeats, base_fails, reference_passes, protected_diff_empty, deterministic, reference_hidden, overall_ok FROM task_validations").fetchall()
    assert len(rows) == 10
    assert all(row == (3, 1, 1, 1, 1, 1, 1) for row in rows)


def test_materialization_pins_deterministic_commits(prepared, tmp_path):
    root, _ = prepared
    second = tmp_path / "pilot"
    shutil.copytree(root / "cases", second / "cases")
    shutil.copy2(ROOT / "manifest.template.toml", second / "manifest.template.toml")
    shutil.copy2(ROOT / "smoke.template.toml", second / "smoke.template.toml")
    _load_script("prepare").prepare_pilot(
        second, model="test-model",
        skill_path=Path(__file__).resolve().parents[1] / "skills/systematic-debugging/v1/SKILL.md",
    )
    for first_path in sorted((root / "generated" / "tasks").glob("*.toml")):
        import tomllib

        first = tomllib.loads(first_path.read_text())
        repeated = tomllib.loads((second / "generated" / "tasks" / first_path.name).read_text())
        assert (first["base_commit"], first["reference_commit"]) == (repeated["base_commit"], repeated["reference_commit"])


def test_manifest_and_60_slot_plan_without_agents(validated, monkeypatch, capsys):
    root, manifest_path, _, _ = validated
    monkeypatch.setattr("forge.experiment.codex_version", lambda *_args: "codex-stub")
    monkeypatch.setattr("forge.scheduler.run_once", lambda *_args, **_kwargs: pytest.fail("plan-only launched an agent"))
    manifest = load_manifest(manifest_path)
    plan = planned_runs(manifest)
    assert len(plan) == 60
    assert Counter(condition for _, condition, *_ in plan) == {"baseline": 30, "skill": 30}
    assert all(Counter((condition, trial) for task_id, condition, trial, *_ in plan if task_id == task) == Counter({(condition, trial): 1 for condition in ("baseline", "skill") for trial in (1, 2, 3)}) for task in {entry[0] for entry in plan})
    capsys.readouterr()
    run_experiment(manifest, plan_only=True)
    assert len(capsys.readouterr().out.splitlines()) == 60
    with sqlite3.connect(manifest.db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM experiment_runs").fetchone()[0] == 60


def test_smoke_manifest_and_six_slot_plan_without_agents(validated, monkeypatch, capsys):
    root, pilot_path, _, _ = validated
    smoke_path = root / "generated" / "smoke.toml"
    monkeypatch.setattr("forge.experiment.codex_version", lambda *_args: "codex-stub")
    monkeypatch.setattr("forge.scheduler.run_once", lambda *_args, **_kwargs: pytest.fail("plan-only launched an agent"))
    pilot = load_manifest(pilot_path)
    smoke = load_manifest(smoke_path)
    assert smoke.db_path != pilot.db_path
    assert smoke.phase == pilot.phase == "pilot"
    assert (smoke.model, smoke.reasoning_effort, smoke.agent, smoke.skill_sha256) == (
        pilot.model, pilot.reasoning_effort, pilot.agent, pilot.skill_sha256,
    )
    assert smoke.trials_per_condition == 1
    assert smoke.max_total_runs == 8 and smoke.max_total_tokens == 150000
    assert {load_task(path).task_id for path in smoke.tasks} == {"parse_tags", "event_dispatch", "weighted_route"}
    plan = planned_runs(smoke)
    assert len(plan) == 6
    assert Counter(condition for _, condition, *_ in plan) == {"baseline": 3, "skill": 3}
    assert {(task, condition, trial) for task, condition, trial, *_ in plan} == {
        (task, condition, 1)
        for task in ("parse_tags", "event_dispatch", "weighted_route")
        for condition in ("baseline", "skill")
    }
    with sqlite3.connect(smoke.db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM task_validations WHERE overall_ok=1").fetchone()[0] == 3
    capsys.readouterr()
    run_experiment(smoke, plan_only=True)
    assert len(capsys.readouterr().out.splitlines()) == 6
    with sqlite3.connect(smoke.db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM experiment_runs").fetchone()[0] == 6
