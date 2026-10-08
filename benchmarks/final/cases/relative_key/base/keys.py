from pathlib import PurePosixPath


def normalize_key(raw):
    if not isinstance(raw, str) or not raw:
        raise ValueError("invalid key")
    path = PurePosixPath(raw)
    if path.is_absolute() or raw.startswith(".."):
        raise ValueError("invalid key")
    return str(path)
