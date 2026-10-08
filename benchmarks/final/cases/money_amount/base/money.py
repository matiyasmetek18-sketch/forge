def parse_amount(text):
    try:
        amount = float(text)
        cents = round(amount * 100)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("invalid amount") from exc
    if not 1 <= cents <= 1_000_000:
        raise ValueError("amount out of range")
    return cents
