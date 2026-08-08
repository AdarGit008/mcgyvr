import re

UNITS = [
    "",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
]
TEENS = [
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
]
ROUND = [
    "",
    "",
    "twenty",
    "thirty",
    "forty",
    "fifty",
    "sixty",
    "seventy",
    "eighty",
    "ninety",
]
IRREGULAR = {
    "one": "first",
    "two": "second",
    "three": "third",
    "five": "fifth",
    "eight": "eighth",
    "nine": "ninth",
    "twelve": "twelfth",
    "hundred": "hundredth",
}


def _counting(value: int) -> str:
    if value < 10:
        return UNITS[value]
    if value < 20:
        return TEENS[value - 10]
    if value < 100:
        tens = ROUND[value // 10]
        unit = value % 10
        return tens if unit == 0 else f"{tens}-{UNITS[unit]}"
    hundreds = UNITS[value // 100]
    rest = value % 100
    if rest == 0:
        return f"{hundreds} hundred"
    return f"{hundreds} hundred and {_counting(rest)}"


def _place_form(piece: str) -> str:
    if piece in IRREGULAR:
        return IRREGULAR[piece]
    if piece.endswith("y"):
        return piece[:-1] + "ieth"
    return piece + "th"


def spell_ordinal_place(place: int) -> str:
    if not isinstance(place, int) or isinstance(place, bool):
        raise ValueError("place must be a whole number")
    if place < 1 or place > 999:
        raise ValueError("place must lie between 1 and 999")
    words = _counting(place)
    tail = re.split(r"[- ]", words)[-1]
    return words[: len(words) - len(tail)] + _place_form(tail)
