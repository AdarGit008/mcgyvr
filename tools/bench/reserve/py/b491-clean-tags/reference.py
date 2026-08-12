def tag_ok(tag: str) -> bool:
    if len(tag) == 0:
        return False
    allowed = "abcdefghijklmnopqrstuvwxyz-"
    for ch in tag.lower():
        if ch not in allowed:
            return False
    return True


def clean_tags(tags: list[str]) -> list[str]:
    """The tags that may be kept, lowered, without repeats."""
    kept = []
    for tag in tags:
        if not tag_ok(tag):
            continue
        lowered = tag.lower()
        if lowered not in kept:
            kept.append(lowered)
    return kept
