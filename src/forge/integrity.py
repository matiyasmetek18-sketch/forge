from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys

from forge.checkout import CheckoutError


PYTEST_CONTROL_FILES = {"conftest.py", "pytest.ini", "tox.ini", "setup.cfg", "pyproject.toml"}


def uses_pytest(command: list[str]) -> bool:
    return any(Path(arg).name in {"pytest", "py.test"} for arg in command)


def uses_unittest(command: list[str]) -> bool:
    return any(Path(arg).name == "unittest" for arg in command)


def restore_protected_paths(
    checkout: Path, commit: str, grader_paths: list[str], pytest_style: bool, unittest_style: bool = False,
) -> list[str]:
    base = _base_files(checkout, commit)
    actual = _actual_files(checkout)
    automatic = set()
    if pytest_style or unittest_style:
        automatic = {
            path for path in base.keys() | actual
            if _python_grader_protected(path, pytest_style, unittest_style)
        }

    explicit = list(dict.fromkeys(grader_paths))
    automatic = {path for path in automatic if not any(_within(path, rel) for rel in explicit)}
    changed: list[str] = []
    for rel in explicit:
        if _changed(checkout, rel, base, actual):
            changed.append(rel)
    for rel in sorted(automatic):
        if _changed(checkout, rel, base, actual):
            changed.append(rel)

    for rel in explicit + sorted(automatic):
        _ensure_parents(checkout, rel)
        target = checkout / rel
        _remove(target)
        tracked = any(_within(path, rel) for path in base)
        if tracked:
            _git(checkout, ["checkout", commit, "--", rel])
    return changed


def _python_grader_protected(rel: str, pytest_style: bool, unittest_style: bool) -> bool:
    name = Path(rel).name
    if name in {"sitecustomize.py", "usercustomize.py"}:
        return True
    if name.endswith(".py") and name[:-3] in sys.stdlib_module_names:
        return True
    if name.endswith(".py") and (name.startswith("test_") or name.endswith("_test.py")):
        return True
    return (pytest_style and name in PYTEST_CONTROL_FILES) or (unittest_style and name.startswith("test") and name.endswith(".py"))


def _within(path: str, parent: str) -> bool:
    return path == parent or path.startswith(parent.rstrip("/") + "/")


def _base_files(checkout: Path, commit: str) -> dict[str, tuple[str, str]]:
    output = _git(checkout, ["ls-tree", "-r", "-z", commit])
    result = {}
    for entry in output.split(b"\0"):
        if entry:
            info, path = entry.split(b"\t", 1)
            mode, kind, oid = info.decode().split()
            if kind == "blob":
                result[os.fsdecode(path)] = (mode, oid)
    return result


def _actual_files(checkout: Path) -> set[str]:
    result: set[str] = set()
    for root, dirs, files in os.walk(checkout, followlinks=False):
        dirs[:] = [name for name in dirs if not (Path(root) == checkout and name == ".git")]
        for name in files + [name for name in dirs if (Path(root) / name).is_symlink()]:
            result.add((Path(root) / name).relative_to(checkout).as_posix())
    return result


def _changed(checkout: Path, rel: str, base: dict[str, tuple[str, str]], actual: set[str]) -> bool:
    expected = {path for path in base if _within(path, rel)}
    present = {path for path in actual if _within(path, rel)}
    if expected != present:
        return True
    for path in expected:
        mode, oid = base[path]
        if _unsafe_parent(checkout, path):
            return True
        target = checkout / path
        if target.is_symlink() != (mode == "120000"):
            return True
        if not target.is_symlink() and bool(target.stat().st_mode & 0o111) != (mode == "100755"):
            return True
        content = os.fsencode(os.readlink(target)) if target.is_symlink() else target.read_bytes()
        if content != _git(checkout, ["cat-file", "blob", oid]):
            return True
    return False


def _remove(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def _ensure_parents(checkout: Path, rel: str) -> None:
    parent = checkout
    for part in Path(rel).parts[:-1]:
        parent /= part
        if parent.is_symlink() or parent.is_file():
            parent.unlink()
        parent.mkdir(exist_ok=True)


def _unsafe_parent(checkout: Path, rel: str) -> bool:
    parent = checkout
    for part in Path(rel).parts[:-1]:
        parent /= part
        if parent.is_symlink() or parent.is_file():
            return True
    return False


def _git(checkout: Path, args: list[str]) -> bytes:
    result = subprocess.run(["git", "-C", str(checkout), *args], capture_output=True)
    if result.returncode:
        raise CheckoutError(result.stderr.decode(errors="replace").strip() or "git integrity operation failed")
    return result.stdout
