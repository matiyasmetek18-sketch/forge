def write_all(writer, data):
    written = writer.write(data)
    if written is None:
        raise RuntimeError("write made no progress")
    return written
