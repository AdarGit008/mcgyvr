def flatline_spans(channel: list[int], least: int) -> list[list[int]]:
    if not isinstance(least, int) or isinstance(least, bool) or least < 2:
        raise ValueError("least must be a whole number of at least two")
    spans: list[list[int]] = []
    start = 0
    for at in range(1, len(channel) + 1):
        if at == len(channel) or channel[at] != channel[at - 1]:
            if at - start >= least:
                spans.append([start, at - 1])
            start = at
    return spans
