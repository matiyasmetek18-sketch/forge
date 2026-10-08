def decode_chunks(chunks):
    return "".join(chunk.decode("utf-8") for chunk in chunks)
