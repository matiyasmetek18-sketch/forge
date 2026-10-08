from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tomllib


FAMILIES = {
    "input-validation", "state-mutation", "algorithm-logic",
    "integration-boundary", "error-edge",
}
SMOKE_TASK_IDS = ("parse_tags", "event_dispatch", "weighted_route")


def _git(repo: Path, *args: str) -> str:
    env = os.environ.copy()
    env.update({
        "GIT_AUTHOR_NAME": "Forge Fixture",
        "GIT_AUTHOR_EMAIL": "fixture@forge.invalid",
        "GIT_COMMITTER_NAME": "Forge Fixture",
        "GIT_COMMITTER_EMAIL": "fixture@forge.invalid",
        "GIT_AUTHOR_DATE": "2026-01-01T00:00:00+00:00",
        "GIT_COMMITTER_DATE": "2026-01-01T00:00:00+00:00",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
    })
    result = subprocess.run(
        ["git", "-C", str(repo), "-c", "commit.gpgsign=false", "-c", "core.autocrlf=false", *args],
        check=True, capture_output=True, text=True, env=env,
    )
    return result.stdout.strip()


def prepare_pilot(root: Path, *, model: str, skill_path: Path) -> Path:
    root = root.resolve()
    skill_path = skill_path.resolve()
    if not model.strip():
        raise ValueError("a pinned model is required")
    skill_path.read_bytes().decode("utf-8")
    cases = sorted((root / "cases").glob("*/case.toml"))
    if len(cases) != 10:
        raise ValueError("the pilot must contain exactly 10 cases")
    generated = root / "generated"
    repos = generated / "repos"
    if repos.exists():
        raise FileExistsError(f"pilot repos already materialized: {repos}")
    tasks_dir = generated / "tasks"
    repos.mkdir(parents=True)
    tasks_dir.mkdir(parents=True)
    task_paths = []
    seen_ids = set()
    family_counts = {family: 0 for family in FAMILIES}
    for case_path in cases:
        case = tomllib.loads(case_path.read_text(encoding="utf-8"))
        task_id = case["task_id"]
        family = case["family"]
        if case["phase"] != "pilot" or case["requires_network"] is not False:
            raise ValueError(f"{task_id}: only offline pilot cases are allowed")
        if family not in FAMILIES or task_id in seen_ids or not task_id.isidentifier():
            raise ValueError(f"{task_id}: invalid or duplicate case identity")
        seen_ids.add(task_id)
        family_counts[family] += 1
        source = case_path.parent
        if not (source / "base").is_dir() or not (source / "reference").is_dir() or not (source / "tests").is_dir():
            raise ValueError(f"{task_id}: missing source or grader")
        repo = repos / task_id
        repo.mkdir()
        _git(repo, "init", "-q")
        for item in (source / "base").rglob("*"):
            if item.is_file():
                target = repo / item.relative_to(source / "base")
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, target)
        shutil.copytree(source / "tests", repo / "tests")
        _git(repo, "add", ".")
        _git(repo, "commit", "-q", "-m", "Buggy base")
        base = _git(repo, "rev-parse", "HEAD")
        for item in (source / "reference").rglob("*"):
            if item.is_file():
                target = repo / item.relative_to(source / "reference")
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, target)
        _git(repo, "add", ".")
        _git(repo, "commit", "-q", "-m", "Reference repair")
        reference = _git(repo, "rev-parse", "HEAD")
        task_path = tasks_dir / f"{task_id}.toml"
        task_path.write_text(
            "".join(f"{key} = {json.dumps(value)}\n" for key, value in {
                "task_id": task_id,
                "version": "pilot-v1",
                "repo_path": str(repo),
                "base_commit": base,
                "reference_commit": reference,
                "agent_prompt": case["agent_prompt"],
                "grader_cmd": ["python3", "-m", "unittest", "discover", "-s", "tests", "-v"],
                "grader_paths": ["tests"],
                "agent_timeout_s": 300,
                "grader_timeout_s": 30,
            }.items()), encoding="utf-8",
        )
        task_paths.append(task_path)
    if any(count != 2 for count in family_counts.values()):
        raise ValueError("the pilot requires two tasks per family")
    template = (root / "manifest.template.toml").read_text(encoding="utf-8")
    manifest = generated / "manifest.toml"
    manifest.write_text(
        template + "\n" + "".join(f"{key} = {json.dumps(value)}\n" for key, value in {
            "db": str(generated / "pilot-v2.sqlite"),
            "tasks": [str(path) for path in task_paths],
            "skill": str(skill_path),
            "skill_id": "systematic-debugging-v1",
            "model": model,
        }.items()), encoding="utf-8",
    )
    smoke_template = (root / "smoke.template.toml").read_text(encoding="utf-8")
    (generated / "smoke.toml").write_text(
        smoke_template + "\n" + "".join(f"{key} = {json.dumps(value)}\n" for key, value in {
            "db": str(generated / "smoke-v2.sqlite"),
            "tasks": [str(tasks_dir / f"{task_id}.toml") for task_id in SMOKE_TASK_IDS],
            "skill": str(skill_path),
            "skill_id": "systematic-debugging-v1",
            "model": model,
        }.items()), encoding="utf-8",
    )
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Materialize the offline Forge debugging pilot")
    parser.add_argument("--model", required=True, help="explicit Codex model to pin for the pilot")
    args = parser.parse_args()
    skill = Path(__file__).resolve().parents[2] / "skills/systematic-debugging/v1/SKILL.md"
    print(prepare_pilot(Path(__file__).resolve().parent, model=args.model, skill_path=skill))
