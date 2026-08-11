import re


def selector_hits(values, selector):
    if not isinstance(values, list) or any(
        isinstance(v, bool) or not isinstance(v, int) for v in values
    ):
        raise ValueError("values must be a list of integers")
    if not isinstance(selector, str) or not selector:
        raise ValueError("selector must be a non-empty string")
    spans = []
    for term in selector.split(","):
        match = re.fullmatch(r"(\d+)(?:-(\d+))?", term)
        if match is None:
            raise ValueError("malformed selector term: " + term)
        low = int(match.group(1))
        high = low if match.group(2) is None else int(match.group(2))
        if low > high:
            raise ValueError("range low end exceeds its high end: " + term)
        spans.append((low, high))
    return sum(1 for v in values if any(lo <= v <= hi for lo, hi in spans))
