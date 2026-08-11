def strip_note(title: str) -> str:
    if not title.endswith(")"):
        return title
    opened = title.rfind("(")
    if opened == -1:
        return title
    return title[:opened].rstrip()
