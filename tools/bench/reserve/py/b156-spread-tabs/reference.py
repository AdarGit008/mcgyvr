def spread_tabs(text: str, width: int) -> str:
    if not isinstance(text, str):
        raise ValueError("text must be a string")
    if not isinstance(width, int) or isinstance(width, bool) or width < 1:
        raise ValueError("width must be a positive whole number")
    out, column = [], 0
    for ch in text:
        if ch == "\t":
            pad = width - column % width
            out.append(" " * pad)
            column += pad
        else:
            out.append(ch)
            column = 0 if ch == "\n" else column + 1
    return "".join(out)
