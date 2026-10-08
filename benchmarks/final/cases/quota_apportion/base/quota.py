def apportion(weights, total):
    if total < 0 or any(weight < 0 for weight in weights) or not weights or sum(weights) == 0:
        raise ValueError("invalid allocation")
    return [round(total * weight / sum(weights)) for weight in weights]
