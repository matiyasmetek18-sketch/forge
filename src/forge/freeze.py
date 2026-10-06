from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import sqlite3
import uuid

from forge.db import _ensure_schema
from forge.experiment import Manifest
from forge.task import InvalidConfigError


def record_freeze(manifest: Manifest, db_path: Path) -> None:
    if db_path.resolve() != manifest.db_path:
        raise InvalidConfigError("freeze --db must match the manifest db path")
    try:
        with sqlite3.connect(db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            _ensure_schema(conn)
            conn.execute(
                "INSERT INTO freezes (freeze_id, manifest_sha256, benchmark_hash, skill_sha256, timestamp) VALUES (?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), manifest.sha256, manifest.benchmark_hash,
                 manifest.skill_sha256, datetime.now(UTC).isoformat()),
            )
    except sqlite3.Error as exc:
        raise RuntimeError(f"DB failure: {exc}") from exc


def require_freeze(manifest: Manifest) -> None:
    if manifest.phase != "final":
        return
    with sqlite3.connect(manifest.db_path) as conn:
        _ensure_schema(conn)
        match = conn.execute(
            "SELECT 1 FROM freezes WHERE manifest_sha256=? AND benchmark_hash=? AND skill_sha256 IS ? LIMIT 1",
            (manifest.sha256, manifest.benchmark_hash, manifest.skill_sha256),
        ).fetchone()
    if match is None:
        raise InvalidConfigError("final phase requires a matching freeze")
