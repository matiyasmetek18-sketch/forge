import json


def load_json(fetch, cached=None):
    etag = cached[1] if cached else None
    response = fetch(etag)
    if response["status"] not in (200, 304):
        raise RuntimeError("request failed")
    data = json.loads(response["body"])
    return data, response.get("etag", etag)
