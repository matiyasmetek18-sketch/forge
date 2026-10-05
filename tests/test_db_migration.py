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

    assert version == 2
    assert len(rows) == 2
    assert tuple(rows[1][name] for name in V1_COLUMNS) == old
    assert rows[0]["run_id"] == "new-run"
    for name in (
        "skill_id", "skill_sha256", "final_prompt_sha256", "prompt_template_version",
        "snapshot_tree_sha", "final_prompt",
    ):
        assert name in columns
        assert rows[1][name] is None
