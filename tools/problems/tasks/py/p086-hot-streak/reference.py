def hot_streak(scores, bar):
    best = [-1, 0]
    start = -1
    for i, score in enumerate(scores):
        if score > bar:
            if start == -1:
                start = i
            length = i - start + 1
            if length > best[1]:
                best = [start, length]
        else:
            start = -1
    return best
