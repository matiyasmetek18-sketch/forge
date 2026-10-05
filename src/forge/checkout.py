from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tempfile
from typing import Iterator


class CheckoutError(Exception):
    """Disposable snapshot setup failed."""


@contextmanager
def disposable_snapshot(repo_path: Path, base_commit: str) -> Iterator[tuple[Path, str, str]]:
    root = Path(tempfile.mkdtemp(prefix="forge-snapshot-"))
    checkout = root / "checkout"
    checkout.mkdir()
    env = _git_environment(root)
    try:
        entries = _git(repo_path, ["ls-tree", "-r", "-z", base_commit], env)
        _git(checkout, ["init", "-q", "--initial-branch=main"], env)
        for entry in entries.split(b"\0"):
            if not entry:
                continue
            info, name = entry.split(b"\t", 1)
            mode, kind, oid = info.decode("ascii").split()
            if kind != "blob" or mode not in {"100644", "100755", "120000"}:
                raise CheckoutError(f"unsupported Git tree entry: {os.fsdecode(name)}")
            rel = os.fsdecode(name)
            target = _safe_target(checkout, rel)
            content = _git(repo_path, ["cat-file", "blob", oid], env)
            if mode == "120000":
                target.symlink_to(os.fsdecode(content))
            else:
                target.write_bytes(content)
                target.chmod(0o755 if mode == "100755" else 0o644)
            new_oid = _git(checkout, ["hash-object", "-w", "--stdin"], env, content).decode("ascii").strip()
            _git(checkout, ["update-index", "--add", "--cacheinfo", mode, new_oid, rel], env)

        tree = _git(checkout, ["write-tree"], env).decode("ascii").strip()
        base_tree = _git(repo_path, ["rev-parse", f"{base_commit}^{{tree}}"], env).decode("ascii").strip()
        if tree != base_tree:
            raise CheckoutError("exported snapshot tree differs from base_commit")
        snapshot_commit = _git(checkout, ["commit-tree", tree, "-m", "Forge task snapshot"], env).decode("ascii").strip()
        _git(checkout, ["update-ref", "refs/heads/main", snapshot_commit], env)
        yield checkout, snapshot_commit, tree
    except subprocess.CalledProcessError as exc:
        raise CheckoutError(exc.stderr.decode(errors="replace").strip() or "Git snapshot setup failed") from exc
    finally:
        shutil.rmtree(root)


def _safe_target(checkout: Path, rel: str) -> Path:
    path = PurePosixPath(rel)
    if path.is_absolute() or not path.parts or any(part in {".", "..", ".git"} for part in path.parts):
        raise CheckoutError(f"unsafe Git tree path: {rel}")
    parent = checkout
    for part in path.parts[:-1]:
        parent /= part
        if parent.is_symlink() or (parent.exists() and not parent.is_dir()):
            raise CheckoutError(f"unsafe Git tree path: {rel}")
        parent.mkdir(exist_ok=True)
    target = parent / path.parts[-1]
    if target.exists() or target.is_symlink():
        raise CheckoutError(f"duplicate Git tree path: {rel}")
    return target


def _git_environment(root: Path) -> dict[str, str]:
    git_home = root / "git-home"
    git_home.mkdir()
    return {
        "PATH": os.environ.get("PATH", os.defpath),
        "HOME": str(git_home),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_AUTHOR_NAME": "Forge Snapshot",
        "GIT_AUTHOR_EMAIL": "forge@localhost",
        "GIT_COMMITTER_NAME": "Forge Snapshot",
        "GIT_COMMITTER_EMAIL": "forge@localhost",
    }


def _git(cwd: Path, args: list[str], env: dict[str, str], data: bytes | None = None) -> bytes:
    result = subprocess.run(["git", "-C", str(cwd), *args], input=data, capture_output=True, env=env, check=True)
    return result.stdout
