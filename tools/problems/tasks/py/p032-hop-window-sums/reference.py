def hop_window_sums(values: list[int], size: int, hop: int) -> list[int]:
    if not isinstance(values, list) or any(
        not isinstance(v, int) or isinstance(v, bool) for v in values
    ):
        raise ValueError("values must be a list of integers")
    if not isinstance(size, int) or isinstance(size, bool) or size < 1:
        raise ValueError("size must be a positive integer")
    if not isinstance(hop, int) or isinstance(hop, bool) or hop < 1:
        raise ValueError("hop must be a positive integer")
    sums = []
    start = 0
    while start + size <= len(values):
        sums.append(sum(values[start : start + size]))
        start += hop
    return sums
