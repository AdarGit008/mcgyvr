def tag_open(marker: str) -> str:
    if not marker.startswith("<") or not marker.endswith(">"):
        raise ValueError("marker must be bracketed")
    inner = marker[1:-1]
    if inner.startswith("/"):
        inner = inner[1:]
    return inner


def tag_pair(opening: str, closing: str) -> bool:
    return tag_open(opening) == tag_open(closing)
