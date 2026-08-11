import re


def swatch_word(hex_text: str, depths: list) -> str:
    if not isinstance(hex_text, str) or re.fullmatch(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})", hex_text) is None:
        raise ValueError("colour must be #rgb or #rrggbb")
    if len(depths) != 3 or any(
        isinstance(d, bool) or not isinstance(d, int) or d < 1 or d > 8 for d in depths
    ):
        raise ValueError("depths must be three widths from 1 to 8")
    digits = hex_text[1:]
    if len(digits) == 3:
        digits = "".join(digit + digit for digit in digits)
    word = 0
    total = 0
    for index, depth in enumerate(depths):
        channel = int(digits[index * 2 : index * 2 + 2], 16)
        word = (word << depth) | (channel >> (8 - depth))
        total += depth
    return format(word, "b").zfill(total)
