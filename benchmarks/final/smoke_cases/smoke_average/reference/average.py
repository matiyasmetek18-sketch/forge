def mean(values):
    if not values:
        raise ValueError("empty values")
    return sum(values) / len(values)
