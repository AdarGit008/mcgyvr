def word_short(word: str, width: int) -> str:
    if len(word) <= width:
        return word
    return word[:width] + "."


def clip_words(words: list[str], width: int) -> str:
    """Every word cut to a width and joined with single spaces."""
    cut = []
    for word in words:
        cut.append(word_short(word, width))
    return " ".join(cut)
