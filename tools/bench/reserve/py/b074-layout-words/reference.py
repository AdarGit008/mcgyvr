def line_width(words):
    total = sum(len(word) for word in words)
    return total + max(len(words) - 1, 0)


def layout_words(words, width):
    if isinstance(width, bool) or not isinstance(width, int) or width <= 0:
        raise ValueError("width must be a positive integer")
    lines = []
    current = []
    for word in words:
        if not isinstance(word, str) or not word:
            raise ValueError("words must be non-empty strings")
        if len(word) > width:
            raise ValueError("word wider than the column: %s" % word)
        if not current or line_width(current + [word]) <= width:
            current.append(word)
        else:
            lines.append(current)
            current = [word]
    if current:
        lines.append(current)
    return lines
