from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3


SCHEMA_VERSION = 3


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
    skill_id: str | None = None
    skill_sha256: str | None = None
    final_prompt_sha256: str | None = None
    prompt_template_version: int | None = None
    snapshot_tree_sha: str | None = None
    final_prompt: str | None = None
    agent_name: str | None = None
    agent_version: str | None = None
    model: str | None = None
    reasoning_effort: str | None = None
    input_tokens: int | None = None
    cached_input_tokens: int | None = None
    output_tokens: int | None = None
    command_count: int | None = None
    file_change_count: int | None = None
    wall_seconds: float | None = None
    telemetry_status: str | None = None
    secret_exposure: int | None = None


RUN_COLUMNS = tuple(RunRecord.__dataclass_fields__)
NEW_COLUMNS = {
    "skill_id": "TEXT",
    "skill_sha256": "TEXT",
    "final_prompt_sha256": "TEXT",
    "prompt_template_version": "INTEGER",
    "snapshot_tree_sha": "TEXT",
    "final_prompt": "TEXT",
    "agent_name": "TEXT",
    "agent_version": "TEXT",
    "model": "TEXT",
    "reasoning_effort": "TEXT",
    "input_tokens": "INTEGER",
    "cached_input_tokens": "INTEGER",
    "output_tokens": "INTEGER",
    "command_count": "INTEGER",
    "file_change_count": "INTEGER",
    "wall_seconds": "REAL",
    "telemetry_status": "TEXT",
    "secret_exposure": "INTEGER",
}


def insert_run(db_path: Path, record: RunRecord) -> None:
    try:
        with sqlite3.connect(db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            _ensure_schema(conn)
            conn.execute(
                f"INSERT INTO runs ({', '.join(RUN_COLUMNS)}) VALUES ({', '.join('?' for _ in RUN_COLUMNS)})",
                tuple(getattr(record, column) for column in RUN_COLUMNS),
            )
    except sqlite3.Error as exc:
        raise RuntimeError(f"DB failure: {exc}") from exc


def _ensure_schema(conn: sqlite3.Connection) -> None:
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version not in (0, 1, 2, SCHEMA_VERSION):
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
            forge_version TEXT NOT NULL,
            skill_id TEXT,
            skill_sha256 TEXT,
            final_prompt_sha256 TEXT,
            prompt_template_version INTEGER,
            snapshot_tree_sha TEXT,
            final_prompt TEXT,
            agent_name TEXT,
            agent_version TEXT,
            model TEXT,
            reasoning_effort TEXT,
            input_tokens INTEGER,
            cached_input_tokens INTEGER,
            output_tokens INTEGER,
            command_count INTEGER,
            file_change_count INTEGER,
            wall_seconds REAL,
            telemetry_status TEXT,
            secret_exposure INTEGER
        )
        """
    )
    if version < SCHEMA_VERSION:
        existing = {row[1] for row in conn.execute("PRAGMA table_info(runs)")}
        for column, sql_type in NEW_COLUMNS.items():
            if column not in existing:
                conn.execute(f"ALTER TABLE runs ADD COLUMN {column} {sql_type}")
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
