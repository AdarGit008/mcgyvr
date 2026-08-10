"""Greedy re-wrap of free text into lines of a fixed width."""


def _paragraphs_of(text):
    paragraphs = []
    words = []
    for line in text.split("\n"):
        tokens = line.split()
        if not tokens:
            if words:
                paragraphs.append(words)
                words = []
        else:
            words.extend(tokens)
    if words:
        paragraphs.append(words)
    return paragraphs


def reflow_text(text: str, width: int) -> list:
    if not isinstance(text, str):
        raise ValueError("text must be a string")
    if isinstance(width, bool) or not isinstance(width, int) or width < 1:
        raise ValueError("width must be a positive integer")
    lines = []
    for position, words in enumerate(_paragraphs_of(text)):
        if position > 0:
            lines.append("")
        current = ""
        for word in words:
            if len(word) > width:
                if current:
                    lines.append(current)
                rest = word
                while len(rest) > width:
                    lines.append(rest[:width])
                    rest = rest[width:]
                current = rest
            elif not current:
                current = word
            elif len(current) + 1 + len(word) <= width:
                current = f"{current} {word}"
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)
    return lines
