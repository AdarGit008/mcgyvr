def score_drop(scores: list) -> int:
    if len(scores) < 2:
        return 0
    lowest = scores[0]
    total = 0
    for score in scores:
        total += score
        if score < lowest:
            lowest = score
    return total - lowest
