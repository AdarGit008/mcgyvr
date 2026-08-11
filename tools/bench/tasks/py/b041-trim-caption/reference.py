"""Shorten a caption to a character budget without splitting a word."""


def trim_caption(text: str, limit: int) -> str:
    if not isinstance(text, str):
        raise ValueError("trim_caption expects a string")
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("limit must be a positive integer")
    if len(text) <= limit:
        return text
    cut = text[: limit - 1]
    if text[limit - 1] != " " and " " in cut:
        cut = cut[: cut.rindex(" ")]
    while cut.endswith(" "):
        cut = cut[:-1]
    return cut + "…"
