from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import signal
import subprocess


@dataclass(frozen=True)
class ProcessResult:
    exit_code: int | None
    timed_out: bool
    stdout_path: Path
    stderr_path: Path


def allowed_environment(home: Path, extra: dict[str, str] | None = None) -> dict[str, str]:
    env: dict[str, str] = {}
    for key in ("PATH", "LANG", "LC_ALL"):
        value = os.environ.get(key)
        if value:
            env[key] = value
    home.mkdir(parents=True, exist_ok=True)
    env["HOME"] = str(home)
    if extra:
        env.update(extra)
    return env


def run_command(
    argv: list[str],
    cwd: Path,
    timeout_s: float,
    stdout_path: Path,
    stderr_path: Path,
    env: dict[str, str],
    stdin_data: bytes | None = None,
) -> ProcessResult:
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        proc = subprocess.Popen(
            argv,
            cwd=str(cwd),
            env=env,
            stdout=stdout,
            stderr=stderr,
            stdin=subprocess.PIPE if stdin_data is not None else None,
            shell=False,
            start_new_session=True,
        )
        try:
            if stdin_data is None:
                exit_code = proc.wait(timeout=timeout_s)
            else:
                proc.communicate(input=stdin_data, timeout=timeout_s)
                exit_code = proc.returncode
            _kill_process_group(proc.pid, signal.SIGKILL)
            return ProcessResult(exit_code, False, stdout_path, stderr_path)
        except subprocess.TimeoutExpired:
            _kill_process_group(proc.pid, signal.SIGKILL)
            try:
                proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                _kill_process_group(proc.pid, signal.SIGKILL)
                proc.wait()
            return ProcessResult(None, True, stdout_path, stderr_path)


def _kill_process_group(pid: int, sig: int = signal.SIGTERM) -> None:
    try:
        os.killpg(pid, sig)
    except ProcessLookupError:
        pass
