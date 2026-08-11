def tidy_path(path: str) -> str:
    if not isinstance(path, str) or path == "":
        raise ValueError("path must be a non-empty string")
    kept = []
    for segment in path.split("/"):
        if segment == "":
            raise ValueError("empty segment in path")
        if segment == "..":
            if not kept:
                raise ValueError("path climbs above its start")
            kept.pop()
        elif segment != ".":
            kept.append(segment)
    return "/".join(kept) if kept else "."
