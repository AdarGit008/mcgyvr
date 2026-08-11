NAMES = [
    "zero",
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


def digit_word(digit: int) -> str:
    return NAMES[digit]


def digit_words(digits: str) -> str:
    words = []
    for ch in digits:
        words.append(digit_word(int(ch)))
    return " ".join(words)
