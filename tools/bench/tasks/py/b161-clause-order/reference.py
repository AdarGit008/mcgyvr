import re


def clause_order(a: str, b: str) -> int:
    for mark in (a, b):
        if not isinstance(mark, str) or re.fullmatch(r"(?:0|[1-9]\d*)(?:\.(?:0|[1-9]\d*))*", mark) is None:
            raise ValueError("malformed clause mark")
    left = [int(piece) for piece in a.split(".")]
    right = [int(piece) for piece in b.split(".")]
    for x, y in zip(left, right):
        if x != y:
            return -1 if x < y else 1
    if len(left) == len(right):
        return 0
    return -1 if len(left) < len(right) else 1
