def path_clean(path: str) -> str:
    kept = []
    for part in path.split("/"):
        if part == "..":
            if kept:
                kept.pop()
        else:
            kept.append(part)
    return "/".join(kept)
