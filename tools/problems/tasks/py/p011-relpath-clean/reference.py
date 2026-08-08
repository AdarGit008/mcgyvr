"""A cleaned form of a slash-separated relative path."""


def normalize_rel_path(path):
    if not isinstance(path, str):
        raise ValueError("normalize_rel_path expects a string")
    if path == "":
        raise ValueError("empty path")
    if path.startswith("/"):
        raise ValueError("path must be relative")
    out = []
    for segment in path.split("/"):
        if segment in ("", "."):
            continue
        if segment == "..":
            if not out:
                raise ValueError("path escapes above its starting point")
            out.pop()
        else:
            out.append(segment)
    return "/".join(out) if out else "."
