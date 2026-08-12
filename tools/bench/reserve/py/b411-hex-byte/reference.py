DIGITS = "0123456789abcdef"


def byte_hex(value: int) -> str:
    return DIGITS[value // 16] + DIGITS[value % 16]


def bytes_hex(values: list) -> str:
    out = ""
    for value in values:
        out += byte_hex(value)
    return out
