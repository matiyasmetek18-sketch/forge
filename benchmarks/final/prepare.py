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


def _git(repo: Path, *args: str) -> str:
    env = os.environ.copy()
    env.update({
        "GIT_AUTHOR_NAME": "Forge Fixture",
        "GIT_AUTHOR_EMAIL": "fixture@forge.invalid",
        "GIT_COMMITTER_NAME": "Forge Fixture",
        "GIT_COMMITTER_EMAIL": "fixture@forge.invalid",
        "GIT_AUTHOR_DATE": "2026-02-01T00:00:00+00:00",
        "GIT_COMMITTER_DATE": "2026-02-01T00:00:00+00:00",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
    })
    result = subprocess.run(
        ["git", "-C", str(repo), "-c", "commit.gpgsign=false", "-c", "core.autocrlf=false", *args],
        check=True, capture_output=True, text=True, env=env,
    )
    return result.stdout.strip()


def _materialize(source: Path, repos: Path, tasks: Path, *, version: str) -> tuple[Path, str]:
    case = tomllib.loads((source / "case.toml").read_text(encoding="utf-8"))
    task_id = case["task_id"]
    repo = repos / task_id
    repo.mkdir(parents=True)
    _git(repo, "init", "-q")
    for item in sorted((source / "base").rglob("*")):
        if item.is_file():
            target = repo / item.relative_to(source / "base")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)
    shutil.copytree(source / "tests", repo / "tests")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "Buggy base")
    base = _git(repo, "rev-parse", "HEAD")
    for item in sorted((source / "reference").rglob("*")):
        if item.is_file():
            target = repo / item.relative_to(source / "reference")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "Reference repair")
    reference = _git(repo, "rev-parse", "HEAD")
    task_path = tasks / f"{task_id}.toml"
    task_path.parent.mkdir(parents=True, exist_ok=True)
    task_path.write_text(
        "".join(f"{key} = {json.dumps(value)}\n" for key, value in {
            "task_id": task_id,
            "version": version,
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
    return task_path, case["family"]


def prepare_final(root: Path, *, model: str, skill_path: Path) -> Path:
    root = root.resolve()
    skill_path = skill_path.resolve()
    if not model.strip():
        raise ValueError("a pinned model is required")
    if __import__("hashlib").sha256(skill_path.read_bytes()).hexdigest() != "a08970b2b2b04a09924097f31537899d1631d289d333408f889407b03a58676e":
        raise ValueError("Systematic Debugging v2 hash mismatch")
    final_cases = sorted((root / "cases").glob("*/case.toml"))
    smoke_cases = sorted((root / "smoke_cases").glob("*/case.toml"))
    if len(final_cases) != 15 or len(smoke_cases) != 3:
        raise ValueError("final requires 15 evidence cases and 3 smoke-only cases")
    generated = root / "generated"
    if generated.exists():
        raise FileExistsError(f"final benchmark already materialized: {generated}")
    final_paths = []
    family_counts = {family: 0 for family in FAMILIES}
    ids = set()
    for case_path in final_cases:
        metadata = tomllib.loads(case_path.read_text(encoding="utf-8"))
        if metadata["phase"] != "final" or metadata["requires_network"] is not False:
            raise ValueError(f"{metadata['task_id']}: invalid final metadata")
        if metadata["task_id"] in ids or metadata["family"] not in FAMILIES:
            raise ValueError(f"{metadata['task_id']}: invalid or duplicate identity")
        ids.add(metadata["task_id"])
        family_counts[metadata["family"]] += 1
        task, _ = _materialize(case_path.parent, generated / "repos" / "final", generated / "tasks" / "final", version="final-v1")
        final_paths.append(task)
    if any(count != 3 for count in family_counts.values()):
        raise ValueError("final requires three tasks per family")
    smoke_paths = []
    for case_path in smoke_cases:
        metadata = tomllib.loads(case_path.read_text(encoding="utf-8"))
        if metadata["phase"] != "smoke" or metadata["requires_network"] is not False or metadata["task_id"] in ids:
            raise ValueError(f"{metadata['task_id']}: invalid smoke metadata")
        ids.add(metadata["task_id"])
        task, _ = _materialize(case_path.parent, generated / "repos" / "smoke", generated / "tasks" / "smoke", version="final-smoke-v1")
        smoke_paths.append(task)
    manifest = generated / "manifest.toml"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        (root / "manifest.template.toml").read_text(encoding="utf-8") + "\n"
        + "".join(f"{key} = {json.dumps(value)}\n" for key, value in {
            "db": str(generated / "final.sqlite"),
            "tasks": [str(path) for path in final_paths],
            "skill": str(skill_path),
            "skill_id": "systematic-debugging-v2",
            "model": model,
        }.items()), encoding="utf-8",
    )
    (generated / "smoke.toml").write_text(
        (root / "smoke.template.toml").read_text(encoding="utf-8") + "\n"
        + "".join(f"{key} = {json.dumps(value)}\n" for key, value in {
            "db": str(generated / "final-smoke.sqlite"),
            "tasks": [str(path) for path in smoke_paths],
            "skill": str(skill_path),
            "skill_id": "systematic-debugging-v2",
            "model": model,
        }.items()), encoding="utf-8",
    )
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Materialize the held-out Forge final benchmark")
    parser.add_argument("--model", required=True)
    args = parser.parse_args()
    skill = Path(__file__).resolve().parents[2] / "skills/systematic-debugging/v2/SKILL.md"
    print(prepare_final(Path(__file__).resolve().parent, model=args.model, skill_path=skill))
