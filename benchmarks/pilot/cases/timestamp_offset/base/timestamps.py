from datetime import datetime, timezone


def normalize_timestamp(text):
    parsed = datetime.fromisoformat(text)
    return parsed.replace(tzinfo=timezone.utc)
