from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Iterator


class WorktreeError(Exception):
    """Git worktree setup or cleanup failed."""


@contextmanager
def disposable_worktree(repo_path: Path, commit: str) -> Iterator[Path]:
    root = Path(tempfile.mkdtemp(prefix="forge-worktree-"))
    worktree = root / "checkout"
    try:
        _git(repo_path, ["worktree", "add", "--detach", str(worktree), commit])
        yield worktree
    except subprocess.CalledProcessError as exc:
        raise WorktreeError(exc.stderr.strip() or "git worktree command failed") from exc
    finally:
        _cleanup_worktree(repo_path, worktree, root)


def protected_paths_modified(worktree: Path, paths: list[str]) -> list[str]:
    changed: list[str] = []
    for rel in paths:
        result = subprocess.run(
            ["git", "-C", str(worktree), "status", "--porcelain", "--", rel],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise WorktreeError(result.stderr.strip() or f"git status failed for {rel}")
        if result.stdout.strip():
            changed.append(rel)
    return changed


def restore_paths(worktree: Path, commit: str, paths: list[str]) -> None:
    for rel in paths:
        result = subprocess.run(
            ["git", "-C", str(worktree), "checkout", commit, "--", rel],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise WorktreeError(result.stderr.strip() or f"failed to restore {rel}")


def _git(repo_path: Path, args: list[str]) -> None:
    subprocess.run(
        ["git", "-C", str(repo_path), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    )


def _cleanup_worktree(repo_path: Path, worktree: Path, root: Path) -> None:
    if worktree.exists():
        subprocess.run(
            ["git", "-C", str(repo_path), "worktree", "remove", "--force", str(worktree)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    subprocess.run(
        ["git", "-C", str(repo_path), "worktree", "prune"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    shutil.rmtree(root, ignore_errors=True)
