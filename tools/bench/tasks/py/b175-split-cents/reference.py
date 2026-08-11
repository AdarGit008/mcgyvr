def split_cents(total, weights):
    if not isinstance(total, int) or isinstance(total, bool): raise ValueError("total must be whole cents")
    if total < 0: raise ValueError("total may not be negative")
    if not isinstance(weights, list) or not weights: raise ValueError("weights must be a non-empty list")
    if not all(isinstance(w, int) and not isinstance(w, bool) and w > 0 for w in weights): raise ValueError("a weight is a positive whole number")
    whole = sum(weights)
    parts = [total * w // whole for w in weights]
    order = sorted(range(len(weights)), key=lambda i: (-(total * weights[i] % whole), i))
    over = total - sum(parts)
    for i in order[:over]:
        parts[i] += 1
    return parts
