def validate_job(payload):
    if not isinstance(payload, dict):
        raise ValueError("job must be a mapping")
    name = payload.get("name")
    retries = payload.get("retries", 3)
    enabled = payload.get("enabled", True)
    if not name or not isinstance(retries, int) or not 0 <= retries <= 5:
        raise ValueError("invalid job")
    return {"name": name, "retries": retries, "enabled": bool(enabled)}
