def validate_job(payload):
    if not isinstance(payload, dict) or set(payload) - {"name", "retries", "enabled"}:
        raise ValueError("job must be a mapping with known fields")
    name = payload.get("name")
    retries = payload.get("retries", 3)
    enabled = payload.get("enabled", True)
    if not isinstance(name, str) or not name or type(retries) is not int or not 0 <= retries <= 5 or type(enabled) is not bool:
        raise ValueError("invalid job")
    return {"name": name, "retries": retries, "enabled": enabled}
