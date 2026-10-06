from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
import platform
from pathlib import Path
import tempfile
import tomllib

from forge import __version__
from forge.codex_adapter import codex_version
from forge.db import insert_experiment
from forge.process import allowed_environment
from forge.task import InvalidConfigError, load_task
from forge.validation import task_identity


@dataclass(frozen=True)
class Manifest:
    path: Path
    text: str
    sha256: str
    experiment_id: str
    phase: str
    db_path: Path
    tasks: tuple[Path, ...]
    task_hashes: tuple[str, ...]
    benchmark_hash: str
    conditions: tuple[str, ...]
    skill_path: Path | None
    skill_id: str | None
    skill_sha256: str | None
    trials_per_condition: int
    seed: int
    agent: str
    argv: tuple[str, ...]
    model: str | None
    reasoning_effort: str | None
    codex_bin: str
    codex_auth: Path | None
    max_total_runs: int
    max_total_tokens: int
    agent_version: str | None


def load_manifest(path: Path) -> Manifest:
    path = path.resolve()
    try:
        raw = path.read_bytes()
        text = raw.decode("utf-8")
        data = tomllib.loads(text)
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise InvalidConfigError("cannot read valid UTF-8 manifest TOML") from exc
    allowed = {
        "experiment_id", "phase", "db", "tasks", "conditions", "skill", "skill_id",
        "trials_per_condition", "seed", "agent", "argv", "model", "reasoning_effort",
        "codex_bin", "codex_auth", "max_total_runs", "max_total_tokens",
    }
    unknown = set(data) - allowed
    if unknown:
        raise InvalidConfigError(f"unknown manifest fields: {', '.join(sorted(unknown))}")

    def string(name: str, required: bool = True) -> str | None:
        value = data.get(name)
        if value is None and not required:
            return None
        if not isinstance(value, str) or not value.strip():
            raise InvalidConfigError(f"{name} must be a nonempty string")
        return value

    def integer(name: str, positive: bool = False) -> int:
        value = data.get(name)
        if type(value) is not int or (positive and value <= 0):
            raise InvalidConfigError(f"{name} must be {'positive' if positive else 'an integer'}")
        return value

    def strings(name: str) -> tuple[str, ...]:
        value = data.get(name)
        if not isinstance(value, list) or not value or not all(isinstance(item, str) and item for item in value):
            raise InvalidConfigError(f"{name} must be a nonempty list of strings")
        return tuple(value)

    experiment_id = string("experiment_id")
    phase = string("phase")
    if phase not in {"pilot", "final"}:
        raise InvalidConfigError("phase must be pilot or final")
    db_path = _resolve(path, string("db"))
    tasks = tuple(_resolve(path, item) for item in strings("tasks"))
    conditions = strings("conditions")
    if len(set(conditions)) != len(conditions) or not set(conditions) <= {"baseline", "skill"}:
        raise InvalidConfigError("conditions must be distinct baseline and/or skill")
    trials = integer("trials_per_condition", positive=True)
    seed = integer("seed")
    max_runs = integer("max_total_runs", positive=True)
    max_tokens = integer("max_total_tokens", positive=True)
    agent = string("agent")
    if agent not in {"cmd", "codex"}:
        raise InvalidConfigError("agent must be cmd or codex")
    skill_name = string("skill", required=False)
    skill_path = _resolve(path, skill_name) if skill_name else None
    skill_id = string("skill_id", required=False)
    if ("skill" in conditions) != (skill_path is not None):
        raise InvalidConfigError("skill path is required exactly when skill condition is present")
    if skill_id is not None and skill_path is None:
        raise InvalidConfigError("skill_id requires skill")
    skill_sha = None
    if skill_path is not None:
        try:
            skill_bytes = skill_path.read_bytes()
            skill_bytes.decode("utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise InvalidConfigError("cannot read UTF-8 skill file") from exc
        skill_sha = hashlib.sha256(skill_bytes).hexdigest()

    argv = strings("argv") if agent == "cmd" else ()
    model = string("model") if agent == "codex" else None
    effort = string("reasoning_effort") if agent == "codex" else None
    codex_bin = string("codex_bin", required=False) or "codex"
    auth_name = string("codex_auth", required=False)
    codex_auth = _resolve(path, auth_name) if auth_name else None
    if agent == "cmd" and any(name in data for name in ("model", "reasoning_effort", "codex_bin", "codex_auth")):
        raise InvalidConfigError("Codex options require agent=codex")
    if agent == "codex" and "argv" in data:
        raise InvalidConfigError("argv requires agent=cmd")

    hashes: list[str] = []
    task_ids: set[str] = set()
    for task_path in tasks:
        task = load_task(task_path)
        if task.task_id in task_ids:
            raise InvalidConfigError(f"duplicate task_id: {task.task_id}")
        task_ids.add(task.task_id)
        hashes.append(task_identity(task_path, task)[4])
    benchmark_hash = hashlib.sha256(json.dumps(sorted(hashes), separators=(",", ":")).encode()).hexdigest()
    agent_version = None
    if agent == "codex":
        with tempfile.TemporaryDirectory(prefix="forge-version-home-") as home:
            agent_version = codex_version(codex_bin, path.parent, allowed_environment(Path(home)), set())
        if agent_version is None:
            raise InvalidConfigError("cannot determine Codex version")
    return Manifest(
        path, text, hashlib.sha256(raw).hexdigest(), experiment_id, phase, db_path,
        tasks, tuple(hashes), benchmark_hash, conditions, skill_path, skill_id,
        skill_sha, trials, seed, agent, argv, model, effort, codex_bin, codex_auth,
        max_runs, max_tokens, agent_version,
    )


def register_experiment(manifest: Manifest) -> None:
    values = {
        "experiment_id": manifest.experiment_id, "phase": manifest.phase,
        "manifest_text": manifest.text, "manifest_sha256": manifest.sha256,
        "benchmark_hash": manifest.benchmark_hash, "skill_sha256": manifest.skill_sha256,
        "agent_name": manifest.agent, "agent_version": manifest.agent_version,
        "model": manifest.model, "reasoning_effort": manifest.reasoning_effort,
        "python_version": platform.python_version(), "os": platform.platform(),
        "forge_version": __version__, "start_time": datetime.now(UTC).isoformat(),
    }
    try:
        insert_experiment(manifest.db_path, values)
    except ValueError as exc:
        raise InvalidConfigError(str(exc)) from exc


def _resolve(manifest_path: Path, name: str) -> Path:
    candidate = Path(name).expanduser()
    return (candidate if candidate.is_absolute() else manifest_path.parent / candidate).resolve()
