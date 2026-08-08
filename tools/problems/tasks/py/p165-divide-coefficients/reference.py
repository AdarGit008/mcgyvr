def _check_run(run: list[int]) -> None:
    if not isinstance(run, list):
        raise ValueError("an ascending run must be a list")
    for coefficient in run:
        if isinstance(coefficient, bool) or not isinstance(coefficient, int):
            raise ValueError("every coefficient must be a whole number")
    if run and run[-1] == 0:
        raise ValueError("an ascending run never ends in a zero")


def _trim(run: list[int]) -> list[int]:
    out = list(run)
    while out and out[-1] == 0:
        out.pop()
    return out


def divide_coefficients(dividend: list[int], divisor: list[int]) -> list[list[int]]:
    _check_run(dividend)
    _check_run(divisor)
    if not divisor:
        raise ValueError("the divisor may not be the empty run")
    rest = list(dividend)
    span = len(dividend) - len(divisor) + 1
    quotient = [0] * span if span > 0 else []
    lead = divisor[-1]
    while rest and len(rest) >= len(divisor):
        shift = len(rest) - len(divisor)
        top = rest[-1]
        if top % lead != 0:
            raise ValueError("the division leaves the whole numbers")
        factor = top // lead
        quotient[shift] = factor
        for i, term in enumerate(divisor):
            rest[shift + i] -= factor * term
        rest = _trim(rest)
    return [_trim(quotient), rest]
