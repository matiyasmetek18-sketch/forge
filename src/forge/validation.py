from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import subprocess
import tempfile
import uuid

from forge import __version__
from forge.checkout import disposable_snapshot
from forge.db import insert_validation
from forge.integrity import _python_grader_protected, _within, uses_pytest, uses_unittest
from forge.process import ProcessResult
from forge.runner import _grade
from forge.task import InvalidConfigError, TaskDefinition, load_task, task_hash


def git_output(repo: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, check=False,
    )
    if result.returncode:
        raise InvalidConfigError("Git could not inspect the task commits")
    return result.stdout


def task_identity(path: Path, task: TaskDefinition) -> tuple[str, str, str, str, str]:
    if task.reference_commit is None:
        raise InvalidConfigError("reference_commit is required for validation")
    base = git_output(task.repo_path, "rev-parse", f"{task.base_commit}^{{commit}}").decode().strip()
    reference = git_output(task.repo_path, "rev-parse", f"{task.reference_commit}^{{commit}}").decode().strip()
    base_tree = git_output(task.repo_path, "rev-parse", f"{base}^{{tree}}").decode().strip()
    reference_tree = git_output(task.repo_path, "rev-parse", f"{reference}^{{tree}}").decode().strip()
    return base, reference, base_tree, reference_tree, task_hash(path, task, base_tree, reference_tree)


def validate_task(path: Path, db_path: Path, repeats: int = 3) -> tuple[bool, str]:
    details: dict[str, object] = {"base": [], "reference": []}
    values: dict[str, object] = {
        "validation_id": str(uuid.uuid4()), "task_id": "unknown", "task_version": "unknown",
        "task_hash": None, "base_commit": None, "reference_commit": None,
        "base_tree_sha": None, "reference_tree_sha": None, "grader_cmd": "[]",
        "repeats": repeats, "base_fails": 0, "reference_passes": 0,
        "protected_diff_empty": 0, "deterministic": 0, "reference_hidden": 0,
        "overall_ok": 0, "timestamp": datetime.now(UTC).isoformat(),
        "forge_version": __version__,
    }
    message = "invalid_config"
    try:
        if repeats < 1:
            raise InvalidConfigError("repeats must be greater than zero")
        task = load_task(path, validate_reference=True)
        values.update(task_id=task.task_id, task_version=task.version, grader_cmd=json.dumps(task.grader_cmd))
        base, reference, base_tree, reference_tree, fingerprint = task_identity(path, task)
        values.update(task_hash=fingerprint, base_commit=base, reference_commit=reference,
                      base_tree_sha=base_tree, reference_tree_sha=reference_tree)
        changed = git_output(task.repo_path, "diff", "--no-ext-diff", "--no-renames", "--name-only", "-z", base, reference)
        protected = [
            name for name in (item.decode("utf-8", errors="surrogateescape") for item in changed.split(b"\0") if item)
            if any(_within(name, path) for path in task.grader_paths)
            or _python_grader_protected(name, uses_pytest(task.grader_cmd), uses_unittest(task.grader_cmd))
        ]
        details["protected_changes"] = protected
        values["protected_diff_empty"] = int(not protected)
        diff = git_output(task.repo_path, "diff", "--no-ext-diff", "--no-renames", "--no-textconv", "--binary", base, reference)
        for label, commit in (("base", base), ("reference", reference)):
            for index in range(repeats):
                with disposable_snapshot(task.repo_path, commit) as (checkout, snapshot_commit, _):
                    with tempfile.TemporaryDirectory(prefix="forge-validation-logs-") as log_root:
                        logs = Path(log_root)
                        if label == "base" and index == 0:
                            values["reference_hidden"] = int(_reference_hidden(checkout, reference.encode(), diff))
                        dummy = ProcessResult(0, False, logs / "unused.out", logs / "unused.err")
                        _, _, status = _grade(checkout, snapshot_commit, task, logs, dummy)
                        details[label].append(status)
        values["base_fails"] = int(all(status == "failed" for status in details["base"]))
        values["reference_passes"] = int(all(status == "passed" for status in details["reference"]))
        values["deterministic"] = int(len(set(details["base"])) == 1 and len(set(details["reference"])) == 1)
        values["overall_ok"] = int(all(values[name] for name in (
            "base_fails", "reference_passes", "protected_diff_empty", "deterministic", "reference_hidden",
        )))
        message = "ok" if values["overall_ok"] else "failed"
    except InvalidConfigError as exc:
        details["error"] = str(exc)
        message = f"invalid_config: {exc}"
    except Exception:
        details["error"] = "validation infrastructure error"
        message = "infra_error"
    values["details"] = json.dumps(details, sort_keys=True)
    insert_validation(db_path, values)
    return bool(values["overall_ok"]), message


def _reference_hidden(checkout: Path, reference: bytes, diff: bytes) -> bool:
    for path in checkout.rglob("*"):
        if path.is_symlink():
            data = str(path.readlink()).encode("utf-8", errors="surrogateescape")
        elif path.is_file():
            data = path.read_bytes()
        else:
            continue
        if reference in data or (diff and diff in data):
            return False
    return True
