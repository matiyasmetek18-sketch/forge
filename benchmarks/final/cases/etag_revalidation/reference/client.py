import json


def load_json(fetch, cached=None):
    etag = cached[1] if cached else None
    response = fetch(etag)
    if response["status"] == 304:
        if cached is None:
            raise RuntimeError("304 without cache")
        return cached
    if response["status"] != 200:
        raise RuntimeError("request failed")
    data = json.loads(response["body"])
    return data, response.get("etag")
