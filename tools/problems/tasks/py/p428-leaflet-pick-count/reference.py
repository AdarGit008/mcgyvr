import re

ITEM = re.compile(r"(\d+)(?:([-+])(\d+))?")
ALLOWED = re.compile(r"[0-9,+-]+")
LAST_PAGE = 9999


def _figure(text: str) -> int:
    if len(text) > 1 and text.startswith("0"):
        raise ValueError(f"the figure {text} carries a leading nought")
    return int(text)


def count_leaflet_picks(picks: str) -> int:
    if not isinstance(picks, str):
        raise ValueError("a pick list must be a string")
    if not picks:
        raise ValueError("a pick list may not be empty")
    if ALLOWED.fullmatch(picks) is None:
        raise ValueError("a pick list holds only digits, commas, hyphens and plus signs")

    pages: set[int] = set()
    for item in picks.split(","):
        if not item:
            raise ValueError("a pick list may not hold an empty item")
        parts = ITEM.fullmatch(item)
        if parts is None:
            raise ValueError(f"the item {item} matches none of the three shapes")
        first = _figure(parts.group(1))
        if first < 1 or first > LAST_PAGE:
            raise ValueError(f"the page {first} falls outside 1 through {LAST_PAGE}")
        if parts.group(2) is None:
            pages.add(first)
            continue
        second = _figure(parts.group(3))
        if parts.group(2) == "-":
            if second < first:
                raise ValueError("a hyphen item may not run backwards")
            last = second
        else:
            if second < 1:
                raise ValueError("a plus item must carry at least one page behind it")
            last = first + second
        if last > LAST_PAGE:
            raise ValueError(f"the page {last} falls outside 1 through {LAST_PAGE}")
        pages.update(range(first, last + 1))
    return len(pages)
