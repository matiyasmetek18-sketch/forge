from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Iterator

from forge.task import InvalidConfigError


def auth_source(explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "auth.json"


def _secret_values(data: bytes) -> set[bytes]:
    try:
        payload = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvalidConfigError("Codex auth file is not valid JSON") from exc

    values: set[bytes] = set()

    def collect(value: object) -> None:
        if isinstance(value, str) and len(value) >= 20:
            values.add(value.encode("utf-8"))
        elif isinstance(value, dict):
            for item in value.values():
                collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)

    collect(payload)
    return values


@contextmanager
def isolated_auth(source: Path) -> Iterator[tuple[Path, set[bytes]]]:
    try:
        data = source.read_bytes()
    except OSError as exc:
        raise InvalidConfigError("Cannot read Codex auth file") from exc
    secrets = _secret_values(data)
    with tempfile.TemporaryDirectory(prefix="forge-codex-home-") as name:
        home = Path(name)
        home.chmod(0o700)
        target = home / "auth.json"
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as output:
            output.write(data)
        try:
            yield home, secrets
        finally:
            refresh_secrets(home, secrets)


def refresh_secrets(home: Path, secrets: set[bytes]) -> None:
    try:
        secrets.update(_secret_values((home / "auth.json").read_bytes()))
    except (OSError, InvalidConfigError):
        pass


def codex_version(binary: str, cwd: Path, env: dict[str, str], secrets: set[bytes]) -> str | None:
    try:
        result = subprocess.run([binary, "--version"], cwd=cwd, env=env, capture_output=True, timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    version = result.stdout.strip()
    if result.returncode or not re.fullmatch(rb"codex-cli [A-Za-z0-9._+-]+", version):
        return None
    if any(secret in version for secret in secrets):
        return None
    return version.decode("ascii")


def parse_telemetry(stdout_path: Path) -> tuple[str, dict[str, int | None]]:
    names = ("input_tokens", "cached_input_tokens", "output_tokens", "command_count", "file_change_count")
    empty = dict.fromkeys(names)
    try:
        lines = stdout_path.read_bytes().splitlines()
    except OSError:
        return "missing", empty
    if not lines:
        return "missing", empty
    totals = {name: 0 for name in names}
    completed = False
    try:
        for line in lines:
            event = json.loads(line)
            if not isinstance(event, dict):
                raise ValueError("invalid event")
            if event.get("type") == "item.completed":
                item = event.get("item")
                if isinstance(item, dict) and item.get("type") == "command_execution":
                    totals["command_count"] += 1
                elif isinstance(item, dict) and item.get("type") == "file_change":
                    totals["file_change_count"] += 1
            elif event.get("type") == "turn.completed":
                usage = event["usage"]
                if not isinstance(usage, dict):
                    raise ValueError("invalid usage")
                for name in ("input_tokens", "cached_input_tokens", "output_tokens"):
                    value = usage[name]
                    if type(value) is not int or value < 0:
                        raise ValueError("invalid token count")
                    totals[name] += value
                completed = True
    except (ValueError, KeyError, TypeError, UnicodeDecodeError):
        return "unparseable", empty
    return ("ok", totals) if completed else ("missing", empty)


def redact_and_detect(paths: list[Path], checkout: Path, secrets: set[bytes]) -> int:
    found = False
    for path in paths:
        try:
            data = path.read_bytes()
        except OSError:
            continue
        if any(secret in data for secret in secrets):
            found = True
            for secret in sorted(secrets, key=len, reverse=True):
                data = data.replace(secret, b"[REDACTED]")
            path.write_bytes(data)
    for path in checkout.rglob("*"):
        if path.is_symlink() or not path.is_file():
            continue
        try:
            data = path.read_bytes()
        except OSError:
            continue
        if any(secret in data for secret in secrets):
            found = True
    return int(found)
