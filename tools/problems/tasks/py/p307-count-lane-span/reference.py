import re


def place(label: str) -> int:
    if len(label) == 0 or len(label) > 3 or re.fullmatch(r"[A-Z]+", label) is None:
        raise ValueError("that is not a lane label")
    value = 0
    for capital in label:
        value = value * 26 + (ord(capital) - 64)
    return value


def count_lane_span(claims: list[str]) -> int:
    if not isinstance(claims, list) or not claims:
        raise ValueError("the batch must be a non-empty list")
    taken = []
    for claim in claims:
        if not isinstance(claim, str):
            raise ValueError("a claim is a string")
        ends = claim.split(":")
        if len(ends) != 2:
            raise ValueError("a claim holds exactly one colon")
        left = place(ends[0])
        right = place(ends[1])
        if left > right:
            raise ValueError("that claim runs backwards")
        taken.append((left, right))
    taken.sort()
    counted = 0
    reached = 0
    for left, right in taken:
        start = left if left > reached else reached + 1
        if right >= start:
            counted += right - start + 1
        if right > reached:
            reached = right
    return counted
