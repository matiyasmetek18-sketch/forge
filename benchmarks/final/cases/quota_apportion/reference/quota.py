def apportion(weights, total):
    if total < 0 or any(weight < 0 for weight in weights) or not weights or sum(weights) == 0:
        raise ValueError("invalid allocation")
    weight_total = sum(weights)
    numerators = [total * weight for weight in weights]
    result = [value // weight_total for value in numerators]
    remaining = total - sum(result)
    order = sorted(range(len(weights)), key=lambda index: (-(numerators[index] % weight_total), index))
    for index in order[:remaining]:
        result[index] += 1
    return result
