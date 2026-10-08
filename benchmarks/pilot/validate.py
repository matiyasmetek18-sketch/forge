from __future__ import annotations

from pathlib import Path
import tomllib

from forge.validation import validate_task


def validate_pilot(root: Path) -> None:
    root = root.resolve()
    tasks = sorted((root / "generated" / "tasks").glob("*.toml"))
    if len(tasks) != 10:
        raise ValueError("materialize all ten pilot tasks before validation")
    db = root / "generated" / "pilot-v2.sqlite"
    failures = []
    for task in tasks:
        ok, message = validate_task(task, db, repeats=3)
        print(f"{task.stem}: {message}")
        if not ok:
            failures.append(task.stem)
    if failures:
        raise RuntimeError("pilot validation failed: " + ", ".join(failures))
    smoke = tomllib.loads((root / "generated" / "smoke.toml").read_text(encoding="utf-8"))
    smoke_failures = []
    for name in smoke["tasks"]:
        task = Path(name)
        ok, message = validate_task(task, Path(smoke["db"]), repeats=3)
        print(f"smoke/{task.stem}: {message}")
        if not ok:
            smoke_failures.append(task.stem)
    if smoke_failures:
        raise RuntimeError("smoke validation failed: " + ", ".join(smoke_failures))


if __name__ == "__main__":
    validate_pilot(Path(__file__).resolve().parent)
