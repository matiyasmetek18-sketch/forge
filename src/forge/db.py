from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3


SCHEMA_VERSION = 1


@dataclass(frozen=True)
class RunRecord:
    run_id: str
    experiment_id: str
    task_id: str
    task_version: str
    condition: str
    trial: int
    seed: int
    base_commit: str
    status: str
    agent_exit_code: int | None
    grader_exit_code: int | None
    protected_paths_modified: str
    start_time: str
    end_time: str
    agent_cmd: str
    stdout_path: str
    stderr_path: str
    forge_version: str


def insert_run(db_path: Path, record: RunRecord) -> None:
    try:
        with sqlite3.connect(db_path) as conn:
            _ensure_schema(conn)
            conn.execute(
                """
                INSERT INTO runs (
                    run_id, experiment_id, task_id, task_version, condition,
                    trial, seed, base_commit, status, agent_exit_code,
                    grader_exit_code, protected_paths_modified, start_time,
                    end_time, agent_cmd, stdout_path, stderr_path, forge_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.run_id,
                    record.experiment_id,
                    record.task_id,
                    record.task_version,
                    record.condition,
                    record.trial,
                    record.seed,
                    record.base_commit,
                    record.status,
                    record.agent_exit_code,
                    record.grader_exit_code,
                    record.protected_paths_modified,
                    record.start_time,
                    record.end_time,
                    record.agent_cmd,
                    record.stdout_path,
                    record.stderr_path,
                    record.forge_version,
                ),
            )
    except sqlite3.Error as exc:
        raise RuntimeError(f"DB failure: {exc}") from exc


def _ensure_schema(conn: sqlite3.Connection) -> None:
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version not in (0, SCHEMA_VERSION):
        raise RuntimeError(f"unsupported schema version: {version}")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS runs (
            run_id TEXT PRIMARY KEY,
            experiment_id TEXT NOT NULL,
            task_id TEXT NOT NULL,
            task_version TEXT NOT NULL,
            condition TEXT NOT NULL,
            trial INTEGER NOT NULL,
            seed INTEGER NOT NULL,
            base_commit TEXT NOT NULL,
            status TEXT NOT NULL,
            agent_exit_code INTEGER,
            grader_exit_code INTEGER,
            protected_paths_modified TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            agent_cmd TEXT NOT NULL,
            stdout_path TEXT NOT NULL,
            stderr_path TEXT NOT NULL,
            forge_version TEXT NOT NULL
        )
        """
    )
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
