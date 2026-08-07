def wrap_text(text: str, width: int) -> list[str]:
    if not isinstance(text, str):
        raise ValueError("wrap_text expects a string")
    if isinstance(width, bool) or not isinstance(width, int) or width < 1:
        raise ValueError("width must be a positive integer")
    if text.startswith(" ") or text.endswith(" ") or "  " in text:
        raise ValueError("text must use single spaces between words")
    lines = []
    current = ""
    for word in text.split(" "):
        if current == "":
            current = word
        elif len(current) + 1 + len(word) <= width:
            current += " " + word
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines
