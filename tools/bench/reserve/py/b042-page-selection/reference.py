import re


def read_span(segment: str) -> list:
    m = re.fullmatch(r"([1-9]\d*)(?:-([1-9]\d*))?", segment)
    if m is None:
        raise ValueError("malformed piece: " + segment)
    low, high = int(m.group(1)), int(m.group(2) or m.group(1))
    if high < low:
        raise ValueError("span runs backwards: " + segment)
    return [low, high]


def expand_selection(spec: str) -> list:
    if not isinstance(spec, str) or not spec:
        raise ValueError("expand_selection expects a non-empty string")
    pages = []
    for piece in spec.split(","):
        low, high = read_span(piece)
        if pages and low <= pages[-1]:
            raise ValueError("selection must move forward: " + piece)
        pages.extend(range(low, high + 1))
    return pages
