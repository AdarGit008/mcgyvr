def smooth_with_taps(samples: list[int], taps: list[int]) -> list[int]:
    if not isinstance(samples, list) or not samples:
        raise ValueError("the series must be a non-empty list")
    for sample in samples:
        if isinstance(sample, bool) or not isinstance(sample, int):
            raise ValueError("every sample is a whole number")
    if not isinstance(taps, list) or not taps:
        raise ValueError("the weights must be a non-empty list")
    for weight in taps:
        if isinstance(weight, bool) or not isinstance(weight, int):
            raise ValueError("every weight is a whole number")
    if len(taps) % 2 == 0:
        raise ValueError("the weights must come to an odd count")

    span = len(samples)
    middle = (len(taps) - 1) // 2
    period = 2 * span - 2 if span > 1 else 1

    def hinge(index: int) -> int:
        if span == 1:
            return 0
        folded = index % period
        if folded >= span:
            folded = period - folded
        return folded

    answer = []
    for at in range(span):
        total = 0
        for tap, weight in enumerate(taps):
            total += samples[hinge(at + tap - middle)] * weight
        answer.append(total)
    return answer
