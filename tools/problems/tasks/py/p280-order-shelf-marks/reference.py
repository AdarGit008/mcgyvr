import re

SHAPE = re.compile(r"([A-Z]{1,3}) ([1-9]\d{0,3})(?:\.(\d{1,4}))? ([a-z])(\d{1,3})")


def order_shelf_marks(marks: list[str]) -> list[str]:
    if not isinstance(marks, list) or not marks:
        raise ValueError("the batch must hold at least one mark")
    keys: dict[str, tuple] = {}
    for mark in marks:
        if not isinstance(mark, str):
            raise ValueError("a mark must be a string")
        if mark in keys:
            raise ValueError("the same mark was handed over twice")
        found = SHAPE.fullmatch(mark)
        if found is None:
            raise ValueError("a mark departs from the Marrow shape")
        fraction = found.group(3) or ""
        if fraction.endswith("0"):
            raise ValueError("a fraction may not finish on a zero")
        keys[mark] = (
            found.group(1),
            int(found.group(2)),
            (fraction + "0000")[:4],
            found.group(4),
            int(found.group(5)),
        )
    return sorted(marks, key=lambda mark: keys[mark])
