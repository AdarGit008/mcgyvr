def code_sum(code: str) -> int:
    figures = "0123456789"
    total = 0
    for ch in code:
        at = figures.find(ch)
        if at >= 0:
            total += at
    return total


def good_codes(codes: list[str]) -> list[str]:
    """The codes whose figure total divides evenly by three."""
    kept = []
    for code in codes:
        if code_sum(code) % 3 == 0:
            kept.append(code)
    return kept
