import re

LETTERS = re.compile(r"[a-z]+")


def hyphenate_word(word: str, rules: list, min_piece: int) -> list:
    if not isinstance(word, str):
        raise ValueError("the word is a string")
    if word == "":
        raise ValueError("the word is not empty")
    if LETTERS.fullmatch(word) is None:
        raise ValueError("the word holds only lowercase letters")
    if not isinstance(rules, list):
        raise ValueError("the rules are a list of patterns")
    if not isinstance(min_piece, int) or isinstance(min_piece, bool) or min_piece < 1:
        raise ValueError("min_piece is a whole number of one or more")

    pairs: list = []
    for pattern in rules:
        if not isinstance(pattern, str):
            raise ValueError("a pattern is a string")
        sides = pattern.split("-")
        if len(sides) != 2:
            raise ValueError("a pattern carries exactly one hyphen")
        if LETTERS.fullmatch(sides[0]) is None or LETTERS.fullmatch(sides[1]) is None:
            raise ValueError("both sides of a pattern are runs of lowercase letters")
        pairs.append((sides[0], sides[1]))

    permitted = [False] * len(word)
    for left, right in pairs:
        for place in range(1, len(word)):
            if word[:place].endswith(left) and word[place:].startswith(right):
                permitted[place] = True

    pieces: list = []
    start = 0
    for place in range(1, len(word)):
        if not permitted[place]:
            continue
        if place - start >= min_piece and len(word) - place >= min_piece:
            pieces.append(word[start:place])
            start = place
    pieces.append(word[start:])
    return pieces
