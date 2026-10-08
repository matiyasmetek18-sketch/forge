import codecs


def decode_chunks(chunks):
    decoder = codecs.getincrementaldecoder("utf-8")()
    pieces = [decoder.decode(chunk, final=False) for chunk in chunks]
    pieces.append(decoder.decode(b"", final=True))
    return "".join(pieces)
