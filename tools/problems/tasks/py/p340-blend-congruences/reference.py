SPAN_CEILING = 1000000000


def _whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _greatest_common(a, b):
    left, right = abs(a), abs(b)
    while right != 0:
        left, right = right, left % right
    return left


def _inverse(value, span):
    if span == 1:
        return 0
    older, newer = span, value % span
    coefficient_older, coefficient_newer = 0, 1
    while newer != 0:
        quotient = older // newer
        older, newer = newer, older - quotient * newer
        coefficient_older, coefficient_newer = (
            coefficient_newer,
            coefficient_older - quotient * coefficient_newer,
        )
    return coefficient_older % span


def blend_congruences(pairs: list) -> list:
    if not isinstance(pairs, list):
        raise ValueError("pairs must be a list")
    if len(pairs) == 0:
        raise ValueError("there is nothing to merge")

    rest, span = 0, 1
    for pair in pairs:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            raise ValueError("every entry must be a pair")
        incoming, width = pair[0], pair[1]
        if not _whole(width) or width < 1 or width > 1000000:
            raise ValueError("a span must be a whole number from 1 through 1000000")
        if not _whole(incoming) or abs(incoming) > SPAN_CEILING:
            raise ValueError("a rest must be a whole number within the limit")

        want = incoming % width
        common = _greatest_common(span, width)
        if (want - rest) % common != 0:
            return []
        merged = (span // common) * width
        if merged > SPAN_CEILING:
            raise ValueError("the merged span swells past the limit")
        reduced = width // common
        shift = ((want - rest) // common) % reduced
        step = (shift * _inverse(span // common, reduced)) % reduced
        rest = (rest + span * step) % merged
        span = merged
    return [rest, span]
