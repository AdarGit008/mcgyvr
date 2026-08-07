import re

PAIRS = ("ch", "ph", "sh", "th", "wh")
LOWER = re.compile(r"[a-z]+")


def _is_vowel(word: str, at: int) -> bool:
    letter = word[at]
    if letter in "aeiou":
        return True
    return letter == "y" and at > 0


def split_syllables(word: str, min_letters: int) -> list:
    if not isinstance(word, str):
        raise ValueError("the word is a string")
    if word == "":
        raise ValueError("the word is not empty")
    if LOWER.fullmatch(word) is None:
        raise ValueError("the word holds only lowercase letters")
    if (
        not isinstance(min_letters, int)
        or isinstance(min_letters, bool)
        or min_letters < 1
    ):
        raise ValueError("min_letters is a whole number of one or more")

    nuclei: list = []
    at = 0
    while at < len(word):
        if _is_vowel(word, at):
            start = at
            while at < len(word) and _is_vowel(word, at):
                at += 1
            nuclei.append((start, at - 1))
        else:
            at += 1
    if len(nuclei) <= 1:
        return [word]

    syllables: list = []
    start = 0
    for index in range(1, len(nuclei)):
        run_start = nuclei[index - 1][1] + 1
        run_end = nuclei[index][0] - 1
        run = run_end - run_start + 1
        if run == 1 or word[run_start : run_start + 2] in PAIRS:
            cut = run_start
        else:
            cut = run_start + 1
        syllables.append(word[start:cut])
        start = cut
    syllables.append(word[start:])

    while len(syllables) > 1:
        short = -1
        for index, piece in enumerate(syllables):
            if len(piece) < min_letters:
                short = index
                break
        if short == -1:
            break
        left = 0 if short == 0 else short - 1
        syllables[left : left + 2] = [syllables[left] + syllables[left + 1]]
    return syllables
