from __future__ import annotations

import sqlite3

from forge.db import RunRecord, insert_run


V1_COLUMNS = (
    "run_id", "experiment_id", "task_id", "task_version", "condition",
    "trial", "seed", "base_commit", "status", "agent_exit_code",
    "grader_exit_code", "protected_paths_modified", "start_time", "end_time",
    "agent_cmd", "stdout_path", "stderr_path", "forge_version",
)


def test_v1_database_migrates_without_losing_rows(tmp_path) -> None:
    db = tmp_path / "legacy.sqlite"
    old = (
        "old-run", "old-exp", "old-task", "v1", "baseline", 4, 17,
        "old-commit", "failed", 0, 1, "[]", "start", "end", "[]",
        "old.stdout", "old.stderr", "0.1.0",
    )
    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            CREATE TABLE runs (
                run_id TEXT PRIMARY KEY, experiment_id TEXT NOT NULL,
                task_id TEXT NOT NULL, task_version TEXT NOT NULL,
                condition TEXT NOT NULL, trial INTEGER NOT NULL,
                seed INTEGER NOT NULL, base_commit TEXT NOT NULL,
                status TEXT NOT NULL, agent_exit_code INTEGER,
                grader_exit_code INTEGER, protected_paths_modified TEXT NOT NULL,
                start_time TEXT NOT NULL, end_time TEXT NOT NULL,
                agent_cmd TEXT NOT NULL, stdout_path TEXT NOT NULL,
                stderr_path TEXT NOT NULL, forge_version TEXT NOT NULL
            )
            """
        )
        conn.execute(f"INSERT INTO runs VALUES ({','.join('?' for _ in old)})", old)
        conn.execute("PRAGMA user_version = 1")

    new = ("new-run", *old[1:])
    insert_run(db, RunRecord(*new))

    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM runs ORDER BY run_id").fetchall()
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        columns = {row[1] for row in conn.execute("PRAGMA table_info(runs)")}

    assert version == 7
    assert len(rows) == 2
    assert tuple(rows[1][name] for name in V1_COLUMNS) == old
    assert rows[0]["run_id"] == "new-run"
    for name in (
        "skill_id", "skill_sha256", "final_prompt_sha256", "prompt_template_version",
        "snapshot_tree_sha", "final_prompt",
    ):
        assert name in columns
        assert rows[1][name] is None


def test_v2_database_migrates_with_existing_row(tmp_path) -> None:
    db = tmp_path / "v2.sqlite"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE runs (" + ", ".join(
            f"{name} TEXT" for name in (*V1_COLUMNS, "skill_id", "skill_sha256", "final_prompt_sha256", "prompt_template_version", "snapshot_tree_sha", "final_prompt")
        ) + ")")
        conn.execute("INSERT INTO runs (run_id, skill_id) VALUES ('prior', 'old-skill')")
        conn.execute("PRAGMA user_version = 2")
    insert_run(db, RunRecord("new", "exp", "task", "1", "baseline", 1, 1, "base", "failed", 0, 1, "[]", "start", "end", "[]", "out", "err", "1"))
    with sqlite3.connect(db) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 7
        assert conn.execute("SELECT skill_id, agent_name, secret_exposure FROM runs WHERE run_id='prior'").fetchone() == ("old-skill", None, None)


def test_v3_database_gains_validations_without_losing_runs(tmp_path) -> None:
    db = tmp_path / "v3.sqlite"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE runs (" + ", ".join(f"{name} TEXT" for name in RunRecord.__dataclass_fields__) + ")")
        conn.execute("INSERT INTO runs (run_id, agent_name) VALUES ('prior', 'codex')")
        conn.execute("PRAGMA user_version = 3")
    insert_run(db, RunRecord("new", "exp", "task", "1", "baseline", 1, 1, "base", "failed", 0, 1, "[]", "start", "end", "[]", "out", "err", "1"))
    with sqlite3.connect(db) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 7
        assert conn.execute("SELECT agent_name FROM runs WHERE run_id='prior'").fetchone() == ("codex",)
        assert conn.execute("SELECT name FROM sqlite_master WHERE name='task_validations'").fetchone() is not None


def test_v4_database_gains_experiments_without_losing_rows(tmp_path) -> None:
    db = tmp_path / "v4.sqlite"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE runs (" + ", ".join(f"{name} TEXT" for name in RunRecord.__dataclass_fields__) + ")")
        conn.execute("INSERT INTO runs (run_id) VALUES ('prior')")
        conn.execute("CREATE TABLE task_validations (validation_id TEXT PRIMARY KEY, task_id TEXT)")
        conn.execute("INSERT INTO task_validations VALUES ('v1', 'task')")
        conn.execute("PRAGMA user_version = 4")
    insert_run(db, RunRecord("new", "exp", "task", "1", "baseline", 1, 1, "base", "failed", 0, 1, "[]", "start", "end", "[]", "out", "err", "1"))
    with sqlite3.connect(db) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 7
        assert conn.execute("SELECT task_id FROM task_validations WHERE validation_id='v1'").fetchone() == ("task",)
        assert conn.execute("SELECT name FROM sqlite_master WHERE name='experiments'").fetchone() is not None


def test_v5_database_gains_plan_without_losing_experiment(tmp_path) -> None:
    db = tmp_path / "v5.sqlite"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE runs (" + ", ".join(f"{name} TEXT" for name in RunRecord.__dataclass_fields__) + ")")
        conn.execute("CREATE TABLE experiments (experiment_id TEXT PRIMARY KEY, manifest_sha256 TEXT)")
        conn.execute("INSERT INTO experiments VALUES ('old', 'hash')")
        conn.execute("PRAGMA user_version = 5")
    insert_run(db, RunRecord("new", "exp", "task", "1", "baseline", 1, 1, "base", "failed", 0, 1, "[]", "start", "end", "[]", "out", "err", "1"))
    with sqlite3.connect(db) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 7
        assert conn.execute("SELECT manifest_sha256 FROM experiments WHERE experiment_id='old'").fetchone() == ("hash",)
        assert conn.execute("SELECT name FROM sqlite_master WHERE name='experiment_runs'").fetchone() is not None


def test_v6_database_gains_freezes_without_losing_plan(tmp_path) -> None:
    db = tmp_path / "v6.sqlite"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE runs (" + ", ".join(f"{name} TEXT" for name in RunRecord.__dataclass_fields__) + ")")
        conn.execute("CREATE TABLE experiment_runs (experiment_id TEXT, task_id TEXT, condition TEXT, trial INTEGER, planned_position INTEGER, run_seed INTEGER, run_id TEXT, attempts INTEGER)")
        conn.execute("INSERT INTO experiment_runs VALUES ('exp', 'task', 'baseline', 1, 0, 7, NULL, 0)")
        conn.execute("PRAGMA user_version = 6")
    insert_run(db, RunRecord("new", "exp", "task", "1", "baseline", 1, 1, "base", "failed", 0, 1, "[]", "start", "end", "[]", "out", "err", "1"))
    with sqlite3.connect(db) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 7
        assert conn.execute("SELECT run_seed FROM experiment_runs").fetchone() == (7,)
        assert conn.execute("SELECT name FROM sqlite_master WHERE name='freezes'").fetchone() is not None
