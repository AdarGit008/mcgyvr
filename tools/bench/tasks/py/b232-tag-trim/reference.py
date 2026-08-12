def tag_trim(tag: str) -> str:
    out = tag
    if out.startswith("#"):
        out = out[1:]
    if out.endswith(":"):
        out = out[:-1]
    return out
