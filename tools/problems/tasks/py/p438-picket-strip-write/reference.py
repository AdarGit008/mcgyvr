def _patterns() -> list:
    table: list = []
    for first in range(5):
        for second in range(first + 1, 5):
            bars = ["w" if bar in (first, second) else "n" for bar in range(5)]
            table.append("".join(bars))
    return table


def write_picket_strip(digits: str) -> dict:
    if not isinstance(digits, str):
        raise ValueError("the digits come as a string")
    if digits == "":
        raise ValueError("there are no digits to draw")
    table = _patterns()
    drawn = ["nn"]
    for character in digits:
        if character < "0" or character > "9":
            raise ValueError("the picket code draws digits only")
        drawn.append(table[int(character)])
    drawn.append("wn")
    strip = "".join(drawn)
    width = sum(2 if bar == "w" else 1 for bar in strip)
    return {"strip": strip, "width": width}
