def _reduce_segments(path):
    stack = []
    for piece in path.split("/"):
        if piece in ("", "."):
            continue
        if piece == "..":
            if not stack:
                raise ValueError(f"path climbs above the root: {path}")
            stack.pop()
        else:
            stack.append(piece)
    return stack


def path_hops(start: str, goal: str) -> int:
    here = _reduce_segments(start)
    there = _reduce_segments(goal)
    shared = 0
    while shared < min(len(here), len(there)) and here[shared] == there[shared]:
        shared += 1
    return len(here) - shared + (len(there) - shared)
