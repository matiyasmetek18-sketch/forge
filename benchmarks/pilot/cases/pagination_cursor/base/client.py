def fetch_all(fetch_page):
    items = []
    cursor = None
    while True:
        page = fetch_page(cursor)
        if not page["items"]:
            break
        items.extend(page["items"])
        cursor = page["next_cursor"]
        if cursor is None:
            break
    return items
