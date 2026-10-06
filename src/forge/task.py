from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import subprocess
import tomllib
from typing import Any


class InvalidConfigError(Exception):
    """Task configuration is invalid."""


@dataclass(frozen=True)
class TaskDefinition:
    task_id: str
    version: str
    repo_path: Path
    base_commit: str
    agent_prompt: str
    grader_cmd: list[str]
    grader_paths: list[str]
    agent_timeout_s: float
    grader_timeout_s: float
    reference_commit: str | None = None


def load_task(path: str | Path) -> TaskDefinition:
    task_path = Path(path)
    try:
        data = tomllib.loads(task_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise InvalidConfigError(f"task file not found: {task_path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise InvalidConfigError(f"invalid TOML in {task_path}: {exc}") from exc

    required = {
        "task_id": str,
        "version": str,
        "repo_path": str,
        "base_commit": str,
        "agent_prompt": str,
        "grader_cmd": list,
        "grader_paths": list,
        "agent_timeout_s": (int, float),
        "grader_timeout_s": (int, float),
    }
    for key, expected_type in required.items():
        if key not in data:
            raise InvalidConfigError(f"missing required field: {key}")
        if not isinstance(data[key], expected_type):
            raise InvalidConfigError(f"field {key} has invalid type")

    grader_cmd = _string_list(data["grader_cmd"], "grader_cmd")
    grader_paths = _string_list(data["grader_paths"], "grader_paths")
    _validate_relative_paths(grader_paths)

    repo_path = Path(data["repo_path"]).expanduser().resolve()
    if not repo_path.exists():
        raise InvalidConfigError(f"repo_path does not exist: {repo_path}")
    if not (repo_path / ".git").exists():
        raise InvalidConfigError(f"repo_path is not a git repository: {repo_path}")

    agent_timeout_s = float(data["agent_timeout_s"])
    grader_timeout_s = float(data["grader_timeout_s"])
    if agent_timeout_s <= 0:
        raise InvalidConfigError("agent_timeout_s must be greater than zero")
    if grader_timeout_s <= 0:
        raise InvalidConfigError("grader_timeout_s must be greater than zero")

    base_commit = data["base_commit"]
    _validate_commit(repo_path, base_commit, "base_commit")
    reference_commit = data.get("reference_commit")
    if reference_commit is not None:
        if not isinstance(reference_commit, str) or not reference_commit:
            raise InvalidConfigError("reference_commit must be a nonempty string")
        _validate_commit(repo_path, reference_commit, "reference_commit")

    return TaskDefinition(
        task_id=data["task_id"],
        version=data["version"],
        repo_path=repo_path,
        base_commit=base_commit,
        agent_prompt=data["agent_prompt"],
        grader_cmd=grader_cmd,
        grader_paths=grader_paths,
        agent_timeout_s=agent_timeout_s,
        grader_timeout_s=grader_timeout_s,
        reference_commit=reference_commit,
    )


def _string_list(value: Any, field: str) -> list[str]:
    if not all(isinstance(item, str) for item in value):
        raise InvalidConfigError(f"field {field} must be a list of strings")
    if not value:
        raise InvalidConfigError(f"field {field} must not be empty")
    return list(value)


def _validate_relative_paths(paths: list[str]) -> None:
    for item in paths:
        path = Path(item)
        if path.is_absolute() or ".." in path.parts:
            raise InvalidConfigError(f"grader path must be repo-relative: {item}")


def _validate_commit(repo_path: Path, commit: str, field: str) -> None:
    result = subprocess.run(
        ["git", "-C", str(repo_path), "cat-file", "-e", f"{commit}^{{commit}}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise InvalidConfigError(f"{field} is not a valid commit: {commit}")


def task_hash(path: Path, task: TaskDefinition, base_tree: str, reference_tree: str) -> str:
    payload = (
        path.read_bytes() + b"\0" + base_tree.encode("ascii") + b"\0"
        + reference_tree.encode("ascii") + b"\0"
        + json.dumps(task.grader_cmd, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    )
    return hashlib.sha256(payload).hexdigest()
