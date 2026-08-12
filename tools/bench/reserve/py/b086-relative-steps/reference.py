def split_absolute(path: str) -> list:
    if not isinstance(path, str) or not path.startswith("/"):
        raise ValueError("expected an absolute path")
    if path == "/":
        return []
    segments = path[1:].split("/")
    for segment in segments:
        if segment in ("", ".", ".."):
            raise ValueError("bad segment: " + segment)
    return segments


def relative_steps(from_dir: str, to_path: str) -> str:
    origin = split_absolute(from_dir)
    goal = split_absolute(to_path)
    shared = 0
    while shared < min(len(origin), len(goal)):
        if origin[shared] != goal[shared]:
            break
        shared += 1
    steps = [".."] * (len(origin) - shared)
    steps.extend(goal[shared:])
    return "/".join(steps) if steps else "."
