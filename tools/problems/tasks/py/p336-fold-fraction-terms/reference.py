SIZE_LIMIT = 1000000000


def _whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def fold_fraction_terms(numerator: int, denominator: int) -> list:
    if not _whole(numerator) or abs(numerator) > SIZE_LIMIT:
        raise ValueError("the numerator must be a whole number within the limit")
    if not _whole(denominator) or denominator < 1 or denominator > SIZE_LIMIT:
        raise ValueError("the denominator must be a whole number from 1 up")

    run = []
    top, bottom = numerator, denominator
    while bottom != 0:
        whole = top // bottom
        rest = top - whole * bottom
        run.append(whole)
        top, bottom = bottom, rest
    return run
