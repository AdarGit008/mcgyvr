def wrap_cost(words: list[str], width: int) -> int:
    if isinstance(width, bool) or not isinstance(width, int) or width < 1:
        raise ValueError("width must be a positive whole number")
    if not words:
        raise ValueError("there is nothing to wrap")
    for word in words:
        if len(word) == 0:
            raise ValueError("an empty word cannot be wrapped")
        if len(word) > width:
            raise ValueError(f"{word!r} does not fit on any line")
    count = len(words)
    best = [None] * count + [0]
    for start in range(count - 1, -1, -1):
        length = 0
        cheapest = None
        for end in range(start, count):
            length += len(words[end]) + (1 if end > start else 0)
            if length > width:
                break
            tail = best[end + 1]
            if tail is None:
                continue
            candidate = (width - length) ** 2 + tail
            if cheapest is None or candidate < cheapest:
                cheapest = candidate
        best[start] = cheapest
    return best[0]
