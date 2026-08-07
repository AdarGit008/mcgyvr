def merge_intervals(intervals: list[list[int]]) -> list[list[int]]:
    """Merge overlapping or touching closed intervals."""
    merged: list[list[int]] = []
    for start, end in sorted(iv[:] for iv in intervals):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return merged
