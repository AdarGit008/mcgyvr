import re


def canonical_stack_mark(mark: str) -> str:
    if not isinstance(mark, str):
        raise ValueError("stack mark must be a string")
    m = re.fullmatch(r"([1-9])(?:-| +)?([nsewNSEW])(?:-| +)?(\d{1,3})", mark)
    if m is None:
        raise ValueError("malformed stack mark")
    stack = int(m.group(3))
    if stack == 0:
        raise ValueError("stack number must be at least 1")
    return m.group(1) + m.group(2).upper() + str(stack).zfill(3)
