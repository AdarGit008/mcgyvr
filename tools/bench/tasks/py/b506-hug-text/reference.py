def hug_text(text: str, mark: str) -> str:
    if (
        text.startswith(mark)
        and text.endswith(mark)
        and len(text) >= len(mark) * 2
    ):
        return text
    return mark + text + mark
