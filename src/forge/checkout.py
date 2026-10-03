from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Iterator


class CheckoutError(Exception):
    """Disposable clone setup failed."""


@contextmanager
def disposable_clone(repo_path: Path, commit: str) -> Iterator[Path]:
    root = Path(tempfile.mkdtemp(prefix="forge-clone-"))
    checkout = root / "checkout"
    try:
        _git(["clone", "--no-hardlinks", "--no-checkout", str(repo_path), str(checkout)])
        _git(["-C", str(checkout), "checkout", "--detach", commit])
        _git(["-C", str(checkout), "remote", "remove", "origin"])
        yield checkout
    except subprocess.CalledProcessError as exc:
        raise CheckoutError(exc.stderr.strip() or "git clone setup failed") from exc
    finally:
        shutil.rmtree(root)


def _git(args: list[str]) -> None:
    subprocess.run(["git", *args], capture_output=True, text=True, check=True)
