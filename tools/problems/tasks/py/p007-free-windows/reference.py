"""The free stretches of a working window, given its busy intervals."""


def free_windows(window_start, window_end, busy):
    for bound in (window_start, window_end):
        if isinstance(bound, bool) or not isinstance(bound, int):
            raise ValueError("window bounds must be integers")
    if window_start >= window_end:
        raise ValueError("window start must precede its end")
    clipped = []
    for start, end in busy:
        for endpoint in (start, end):
            if isinstance(endpoint, bool) or not isinstance(endpoint, int):
                raise ValueError("busy endpoints must be integers")
        if start >= end:
            raise ValueError("busy start must precede its end")
        low = max(start, window_start)
        high = min(end, window_end)
        if low < high:
            clipped.append((low, high))
    clipped.sort()
    gaps = []
    cursor = window_start
    for start, end in clipped:
        if start > cursor:
            gaps.append([cursor, start])
        if end > cursor:
            cursor = end
    if cursor < window_end:
        gaps.append([cursor, window_end])
    return gaps
