_GROUPS = (
    ("bfpv", "1"),
    ("cgjkqsxz", "2"),
    ("dt", "3"),
    ("l", "4"),
    ("mn", "5"),
    ("r", "6"),
)


def _digit_for(letter):
    for letters, digit in _GROUPS:
        if letter in letters:
            return digit
    return ""


def soundex_code(word: str) -> str:
    if not isinstance(word, str):
        raise ValueError("soundex_code expects a string")
    if word == "" or not word.isascii() or not word.isalpha():
        raise ValueError("word must be one or more ASCII letters")
    lower = word.lower()
    result = lower[0].upper()
    previous = _digit_for(lower[0])
    for letter in lower[1:]:
        if letter in "hw":
            continue
        digit = _digit_for(letter)
        if digit == "":
            previous = ""
            continue
        if digit != previous:
            result += digit
        previous = digit
    return (result + "000")[:4]
