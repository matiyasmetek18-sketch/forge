from __future__ import annotations

from pathlib import Path
import json
import random
import sqlite3

from forge.codex_adapter import auth_source
from forge.db import _ensure_schema
from forge.experiment import Manifest, load_manifest, register_experiment
from forge.freeze import require_freeze
from forge.runner import RunOnceRequest, run_once
from forge.task import InvalidConfigError, load_task


class CredentialError(Exception):
    """Codex authentication needs user attention."""


def preflight(manifest: Manifest) -> None:
    needed: list[str] = []
    with sqlite3.connect(manifest.db_path) as conn:
        _ensure_schema(conn)
        for path, fingerprint in zip(manifest.tasks, manifest.task_hashes):
            task = load_task(path)
            valid = conn.execute(
                "SELECT 1 FROM task_validations WHERE task_id=? AND task_hash=? AND overall_ok=1 LIMIT 1",
                (task.task_id, fingerprint),
            ).fetchone()
            if valid is None:
                needed.append(task.task_id)
    if needed:
        raise InvalidConfigError("tasks need validating: " + ", ".join(needed))


def planned_runs(manifest: Manifest) -> list[tuple[str, str, int, int, int]]:
    rng = random.Random(manifest.seed)
    tasks = [load_task(path).task_id for path in manifest.tasks]
    by_condition: dict[str, list[tuple[str, str, int]]] = {}
    for condition in manifest.conditions:
        entries = [(task_id, condition, trial) for task_id in tasks for trial in range(1, manifest.trials_per_condition + 1)]
        rng.shuffle(entries)
        by_condition[condition] = entries
    order = list(manifest.conditions)
    rng.shuffle(order)
    plan: list[tuple[str, str, int, int, int]] = []
    while any(by_condition.values()):
        for condition in order:
            if by_condition[condition]:
                task_id, _, trial = by_condition[condition].pop()
                plan.append((task_id, condition, trial, len(plan), rng.getrandbits(63)))
    return plan


def persist_plan(manifest: Manifest) -> None:
    expected = planned_runs(manifest)
    try:
        with sqlite3.connect(manifest.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            _ensure_schema(conn)
            existing = conn.execute(
                "SELECT task_id, condition, trial, planned_position, run_seed FROM experiment_runs WHERE experiment_id=? ORDER BY planned_position",
                (manifest.experiment_id,),
            ).fetchall()
            if existing:
                if existing != expected:
                    raise InvalidConfigError("stored plan differs from manifest and seed")
                return
            conn.executemany(
                "INSERT INTO experiment_runs (experiment_id, task_id, condition, trial, planned_position, run_seed) VALUES (?, ?, ?, ?, ?, ?)",
                [(manifest.experiment_id, *entry) for entry in expected],
            )
    except sqlite3.Error as exc:
        raise RuntimeError(f"DB failure: {exc}") from exc


def _rows(manifest: Manifest) -> list[sqlite3.Row]:
    with sqlite3.connect(manifest.db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM experiment_runs WHERE experiment_id=? ORDER BY planned_position",
            (manifest.experiment_id,),
        ).fetchall()
    return rows


def _reconcile(manifest: Manifest) -> None:
    with sqlite3.connect(manifest.db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        for row in _rows(manifest):
            attempts = conn.execute(
                "SELECT run_id FROM runs WHERE experiment_id=? AND task_id=? AND condition=? AND trial=? AND seed=? ORDER BY start_time, run_id",
                (manifest.experiment_id, row["task_id"], row["condition"], row["trial"], row["run_seed"]),
            ).fetchall()
            if len(attempts) > row["attempts"]:
                conn.execute(
                    "UPDATE experiment_runs SET attempts=?, run_id=? WHERE experiment_id=? AND task_id=? AND condition=? AND trial=?",
                    (len(attempts), attempts[-1][0], manifest.experiment_id, row["task_id"], row["condition"], row["trial"]),
                )


def _last_status(manifest: Manifest, row: sqlite3.Row) -> str | None:
    if row["run_id"] is None:
        return None
    with sqlite3.connect(manifest.db_path) as conn:
        result = conn.execute("SELECT status FROM runs WHERE run_id=?", (row["run_id"],)).fetchone()
    return result[0] if result else None


def _spent(manifest: Manifest) -> tuple[int, int]:
    with sqlite3.connect(manifest.db_path) as conn:
        count, tokens = conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(COALESCE(input_tokens, 0) + COALESCE(output_tokens, 0)), 0) FROM runs WHERE experiment_id=?",
            (manifest.experiment_id,),
        ).fetchone()
    return count, tokens


def _link(manifest: Manifest, row: sqlite3.Row, run_id: str) -> None:
    with sqlite3.connect(manifest.db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "UPDATE experiment_runs SET run_id=?, attempts=attempts+1 WHERE experiment_id=? AND task_id=? AND condition=? AND trial=?",
            (run_id, manifest.experiment_id, row["task_id"], row["condition"], row["trial"]),
        )


def _credential_failed(manifest: Manifest, run_id: str) -> bool:
    if manifest.agent != "codex":
        return False
    with sqlite3.connect(manifest.db_path) as conn:
        record = conn.execute("SELECT status, stderr_path FROM runs WHERE run_id=?", (run_id,)).fetchone()
    if record is None or record[0] != "agent_error":
        return False
    try:
        stderr = Path(record[1]).read_bytes().lower()
    except OSError:
        return False
    return any(marker in stderr for marker in (b"authentication failed", b"not logged in", b"refresh token"))


def _require_unchanged_inputs(manifest: Manifest) -> None:
    current = load_manifest(manifest.path)
    if (current.sha256, current.benchmark_hash, current.skill_sha256, current.agent_version) != (
        manifest.sha256, manifest.benchmark_hash, manifest.skill_sha256, manifest.agent_version,
    ):
        raise InvalidConfigError("experiment inputs changed after planning")


def run_experiment(manifest: Manifest, *, limit: int | None = None, plan_only: bool = False) -> None:
    if limit is not None and limit < 1:
        raise InvalidConfigError("--limit must be greater than zero")
    require_freeze(manifest)
    preflight(manifest)
    _require_unchanged_inputs(manifest)
    register_experiment(manifest)
    persist_plan(manifest)
    _reconcile(manifest)
    rows = _rows(manifest)
    if plan_only:
        for row in rows:
            print(f"{row['planned_position']:>3} {row['task_id']} {row['condition']} trial={row['trial']} seed={row['run_seed']}")
        return

    by_task = {load_task(path).task_id: path for path in manifest.tasks}
    executed = 0
    stop_reason = None
    for original in rows:
        while True:
            row = next(item for item in _rows(manifest) if item["planned_position"] == original["planned_position"])
            prior = _last_status(manifest, row)
            if prior is not None and (prior != "infra_error" or row["attempts"] >= 2):
                break
            if limit is not None and executed >= limit:
                stop_reason = "limit reached"
                break
            count, tokens = _spent(manifest)
            if count >= manifest.max_total_runs:
                stop_reason = "max_total_runs reached"
                break
            if tokens >= manifest.max_total_tokens:
                stop_reason = "max_total_tokens reached"
                break
            _require_unchanged_inputs(manifest)
            if manifest.agent == "codex":
                try:
                    auth = json.loads(auth_source(manifest.codex_auth).read_bytes())
                except (OSError, ValueError, UnicodeDecodeError) as exc:
                    raise CredentialError("Codex auth file is unavailable or invalid") from exc
                if not isinstance(auth, dict) or not auth:
                    raise CredentialError("Codex auth file is unavailable or invalid")
            result = run_once(RunOnceRequest(
                task_path=by_task[row["task_id"]], condition=row["condition"],
                trial=row["trial"], seed=row["run_seed"], experiment_id=manifest.experiment_id,
                db_path=manifest.db_path, agent_cmd=list(manifest.argv),
                skill_path=manifest.skill_path if row["condition"] == "skill" else None,
                skill_id=manifest.skill_id if row["condition"] == "skill" else None,
                agent="codex" if manifest.agent == "codex" else None,
                model=manifest.model, reasoning_effort=manifest.reasoning_effort,
                codex_bin=manifest.codex_bin, codex_auth=manifest.codex_auth,
            ))
            _link(manifest, row, result.run_id)
            executed += 1
            print(f"{row['planned_position'] + 1}/{len(rows)} {row['task_id']} {row['condition']} trial={row['trial']} {result.status}")
            if _credential_failed(manifest, result.run_id):
                raise CredentialError("Codex authentication failed")
            if result.status != "infra_error":
                break
        if stop_reason:
            break
    if stop_reason:
        print(f"stopped: {stop_reason}; resume with run-experiment {manifest.path}")
    _print_summary(manifest)


def _print_summary(manifest: Manifest) -> None:
    print("condition runs passed failed errors input_tokens output_tokens")
    with sqlite3.connect(manifest.db_path) as conn:
        for condition in manifest.conditions:
            row = conn.execute(
                """
                SELECT COUNT(*), SUM(CASE WHEN status='passed' THEN 1 ELSE 0 END),
                       SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END),
                       SUM(CASE WHEN status NOT IN ('passed','failed') THEN 1 ELSE 0 END),
                       COALESCE(SUM(input_tokens),0), COALESCE(SUM(output_tokens),0)
                FROM runs WHERE experiment_id=? AND condition=?
                """,
                (manifest.experiment_id, condition),
            ).fetchone()
            print(condition, *(value or 0 for value in row))
