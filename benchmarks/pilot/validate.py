from __future__ import annotations

from pathlib import Path

from forge.validation import validate_task


def validate_pilot(root: Path) -> None:
    root = root.resolve()
    tasks = sorted((root / "generated" / "tasks").glob("*.toml"))
    if len(tasks) != 10:
        raise ValueError("materialize all ten pilot tasks before validation")
    db = root / "generated" / "pilot.sqlite"
    failures = []
    for task in tasks:
        ok, message = validate_task(task, db, repeats=3)
        print(f"{task.stem}: {message}")
        if not ok:
            failures.append(task.stem)
    if failures:
        raise RuntimeError("pilot validation failed: " + ", ".join(failures))


if __name__ == "__main__":
    validate_pilot(Path(__file__).resolve().parent)
