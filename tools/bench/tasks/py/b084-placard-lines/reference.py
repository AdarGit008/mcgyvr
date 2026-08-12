"""Lay a notice's text into placard lines."""


def placard_lines(text, width):
    if not isinstance(text, str) or text == "":
        raise ValueError("placard_lines expects a non-empty string")
    if isinstance(width, bool) or not isinstance(width, int) or width <= 0:
        raise ValueError("width must be a positive integer")
    if text.startswith(" ") or text.endswith(" ") or "  " in text:
        raise ValueError("words must be separated by single spaces")
    lines = []
    line = ""
    for word in text.split(" "):
        if len(word) > width:
            raise ValueError("word wider than the placard: " + word)
        if line == "":
            line = word
        elif len(line) + 1 + len(word) <= width:
            line = line + " " + word
        else:
            lines.append(line)
            line = word
    lines.append(line)
    return lines
