def write_all(writer, data):
    view = memoryview(data)
    total = 0
    while total < len(view):
        written = writer.write(view[total:])
        if written is None or written <= 0:
            raise RuntimeError("write made no progress")
        total += written
    return total
