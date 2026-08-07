import re

SEGMENT = re.compile(r"(!?)(\d+)(?:-(\d+))?")
LAST_SHEET = 9999


def _figure(text: str) -> int:
    if len(text) > 1 and text.startswith("0"):
        raise ValueError(f"the figure {text} carries a leading nought")
    value = int(text)
    if value < 1 or value > LAST_SHEET:
        raise ValueError(f"the sheet {value} falls outside 1 through {LAST_SHEET}")
    return value


def merge_sheet_marks(marks: list[str]) -> dict:
    if not isinstance(marks, list):
        raise ValueError("the marks must be a list of strings")
    held: set[int] = set()
    for mark in marks:
        if not isinstance(mark, str):
            raise ValueError("a mark must be a string")
        if not mark:
            raise ValueError("a mark may not be empty")
        if mark.startswith(" ") or mark.endswith(" ") or "  " in mark:
            raise ValueError("segments are parted by exactly one blank apiece")
        for segment in mark.split(" "):
            parts = SEGMENT.fullmatch(segment)
            if parts is None:
                raise ValueError(
                    f"the segment {segment} matches none of the four shapes"
                )
            first = _figure(parts.group(2))
            last = first if parts.group(3) is None else _figure(parts.group(3))
            if last < first:
                raise ValueError("a hyphen segment may not run backwards")
            span = range(first, last + 1)
            if parts.group(1) == "!":
                held.difference_update(span)
            else:
                held.update(span)

    ordered = sorted(held)
    runs: list[str] = []
    index = 0
    while index < len(ordered):
        end = index
        while end + 1 < len(ordered) and ordered[end + 1] == ordered[end] + 1:
            end += 1
        runs.append(
            str(ordered[index]) if index == end else f"{ordered[index]}-{ordered[end]}"
        )
        index = end + 1
    return {"spec": " ".join(runs), "sheets": len(ordered)}
