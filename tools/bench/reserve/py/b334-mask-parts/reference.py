def mask_word(word: str) -> str:
    if len(word) <= 2:
        return word
    return word[0] + "." * (len(word) - 2) + word[-1]


def mask_line(line: str) -> str:
    return " ".join(mask_word(word) for word in line.split())
