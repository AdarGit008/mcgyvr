def grace_window(counts, goal, grace):
    if goal <= 0:
        raise ValueError("goal must be positive")
    if grace < 0:
        raise ValueError("grace must not be negative")
    kept = [day for day, count in enumerate(counts) if count >= goal]
    best = 0
    left = 0
    for right in range(len(kept)):
        while kept[right] - kept[left] - (right - left) > grace:
            left += 1
        best = max(best, kept[right] - kept[left] + 1)
    return best
