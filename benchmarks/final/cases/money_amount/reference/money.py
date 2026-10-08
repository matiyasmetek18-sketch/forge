import re


AMOUNT = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]{1,2})?\Z")


def parse_amount(text):
    if not isinstance(text, str) or AMOUNT.fullmatch(text) is None:
        raise ValueError("invalid amount")
    whole, separator, fraction = text.partition(".")
    cents = int(whole) * 100 + int((fraction + "00")[:2] if separator else "00")
    if not 1 <= cents <= 1_000_000:
        raise ValueError("amount out of range")
    return cents
