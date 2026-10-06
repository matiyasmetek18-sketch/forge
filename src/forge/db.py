from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3


SCHEMA_VERSION = 7


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


VALIDATION_COLUMNS = (
    "validation_id", "task_id", "task_version", "task_hash", "base_commit",
    "reference_commit", "base_tree_sha", "reference_tree_sha", "grader_cmd",
    "repeats", "base_fails", "reference_passes", "protected_diff_empty",
    "deterministic", "reference_hidden", "overall_ok", "details", "timestamp",
    "forge_version",
)


def insert_validation(db_path: Path, values: dict[str, object]) -> None:
    try:
        with sqlite3.connect(db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            _ensure_schema(conn)
            conn.execute(
                f"INSERT INTO task_validations ({', '.join(VALIDATION_COLUMNS)}) VALUES ({', '.join('?' for _ in VALIDATION_COLUMNS)})",
                tuple(values.get(column) for column in VALIDATION_COLUMNS),
            )
    except sqlite3.Error as exc:
        raise RuntimeError(f"DB failure: {exc}") from exc


EXPERIMENT_COLUMNS = (
    "experiment_id", "phase", "manifest_text", "manifest_sha256", "benchmark_hash",
    "skill_sha256", "agent_name", "agent_version", "model", "reasoning_effort",
    "python_version", "os", "forge_version", "start_time",
)


def insert_experiment(db_path: Path, values: dict[str, object]) -> None:
    try:
        with sqlite3.connect(db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            _ensure_schema(conn)
            existing = conn.execute("SELECT manifest_sha256, benchmark_hash, skill_sha256 FROM experiments WHERE experiment_id = ?", (values["experiment_id"],)).fetchone()
            if existing is not None:
                if existing[0] != values["manifest_sha256"]:
                    raise ValueError("experiment_id already exists with a different manifest")
                if existing[1:] != (values["benchmark_hash"], values["skill_sha256"]):
                    raise ValueError("experiment inputs changed under the same manifest")
                return
            conn.execute(
                f"INSERT INTO experiments ({', '.join(EXPERIMENT_COLUMNS)}) VALUES ({', '.join('?' for _ in EXPERIMENT_COLUMNS)})",
                tuple(values.get(column) for column in EXPERIMENT_COLUMNS),
            )
    except sqlite3.Error as exc:
        raise RuntimeError(f"DB failure: {exc}") from exc


def _ensure_schema(conn: sqlite3.Connection) -> None:
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version not in (0, 1, 2, 3, 4, 5, 6, SCHEMA_VERSION):
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
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS experiments (
            experiment_id TEXT PRIMARY KEY,
            phase TEXT NOT NULL,
            manifest_text TEXT NOT NULL,
            manifest_sha256 TEXT NOT NULL,
            benchmark_hash TEXT NOT NULL,
            skill_sha256 TEXT,
            agent_name TEXT NOT NULL,
            agent_version TEXT,
            model TEXT,
            reasoning_effort TEXT,
            python_version TEXT NOT NULL,
            os TEXT NOT NULL,
            forge_version TEXT NOT NULL,
            start_time TEXT NOT NULL
        )
        """
    )
    if version < SCHEMA_VERSION:
        existing = {row[1] for row in conn.execute("PRAGMA table_info(runs)")}
        for column, sql_type in NEW_COLUMNS.items():
            if column not in existing:
                conn.execute(f"ALTER TABLE runs ADD COLUMN {column} {sql_type}")
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS task_validations (
            validation_id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            task_version TEXT NOT NULL,
            task_hash TEXT,
            base_commit TEXT,
            reference_commit TEXT,
            base_tree_sha TEXT,
            reference_tree_sha TEXT,
            grader_cmd TEXT NOT NULL,
            repeats INTEGER NOT NULL,
            base_fails INTEGER NOT NULL,
            reference_passes INTEGER NOT NULL,
            protected_diff_empty INTEGER NOT NULL,
            deterministic INTEGER NOT NULL,
            reference_hidden INTEGER NOT NULL,
            overall_ok INTEGER NOT NULL,
            details TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            forge_version TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS experiment_runs (
            experiment_id TEXT NOT NULL,
            task_id TEXT NOT NULL,
            condition TEXT NOT NULL,
            trial INTEGER NOT NULL,
            planned_position INTEGER NOT NULL,
            run_seed INTEGER NOT NULL,
            run_id TEXT,
            attempts INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (experiment_id, task_id, condition, trial),
            UNIQUE (experiment_id, planned_position)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS freezes (
            freeze_id TEXT PRIMARY KEY,
            manifest_sha256 TEXT NOT NULL,
            benchmark_hash TEXT NOT NULL,
            skill_sha256 TEXT,
            timestamp TEXT NOT NULL
        )
        """
    )
