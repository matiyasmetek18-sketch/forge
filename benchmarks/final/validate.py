from __future__ import annotations

from pathlib import Path
import tomllib

from forge.validation import validate_task


def validate_final(root: Path) -> None:
    root = root.resolve()
    for manifest_name in ("manifest.toml", "smoke.toml"):
        manifest = tomllib.loads((root / "generated" / manifest_name).read_text(encoding="utf-8"))
        failures = []
        for name in manifest["tasks"]:
            task = Path(name)
            ok, message = validate_task(task, Path(manifest["db"]), repeats=3)
            print(f"{manifest_name}/{task.stem}: {message}")
            if not ok:
                failures.append(task.stem)
        if failures:
            raise RuntimeError(f"{manifest_name} validation failed: " + ", ".join(failures))


if __name__ == "__main__":
    validate_final(Path(__file__).resolve().parent)
