"""Gap widths that justify a paragraph's lines to a column."""


def justify_spacing(width, lines):
    if isinstance(width, bool) or not isinstance(width, int) or width <= 0:
        raise ValueError("width must be a positive integer")
    if not isinstance(lines, list) or not lines:
        raise ValueError("a paragraph is a non-empty list of lines")
    spacing = []
    for row, line in enumerate(lines):
        if not isinstance(line, list) or not line:
            raise ValueError("a line is a non-empty list of words")
        letters = 0
        for word in line:
            if not isinstance(word, str) or word == "":
                raise ValueError("a word must be a non-empty string")
            if " " in word:
                raise ValueError("a word must not contain spaces")
            letters += len(word)
        gap_count = len(line) - 1
        min_width = letters + gap_count
        if min_width > width:
            raise ValueError("a line must fit its width")
        if gap_count == 0 or row == len(lines) - 1:
            spacing.append([1] * gap_count)
        else:
            spare = width - letters
            base = spare // gap_count
            bump = spare % gap_count
            gaps = []
            for i in range(gap_count):
                gaps.append(base + 1 if i < bump else base)
            spacing.append(gaps)
    return spacing
