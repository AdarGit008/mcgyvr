GLYPHS = "0123456789ABCDEFGHIJ"


def whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def expand_fraction_digits(numerator: int, denominator: int, base: int) -> str:
    if not whole(numerator) or not whole(denominator) or not whole(base):
        raise ValueError("all three arguments must be whole numbers")
    if base < 3 or base > 20:
        raise ValueError("base must lie in 3..20")
    if denominator < 1:
        raise ValueError("denominator must be a positive whole number")
    if abs(numerator) > 1000000 or denominator > 1000000:
        raise ValueError("magnitudes must stay at or below one million")

    negative = numerator < 0
    magnitude = abs(numerator)
    head = magnitude // denominator
    rest = magnitude % denominator

    stem = ""
    if head == 0:
        stem = "0"
    else:
        while head > 0:
            stem = GLYPHS[head % base] + stem
            head //= base
    if rest == 0:
        return ("-" if negative else "") + stem

    seen = {}
    tail = []
    carry = rest
    repeat = -1
    while carry != 0:
        if carry in seen:
            repeat = seen[carry]
            break
        seen[carry] = len(tail)
        scaled = carry * base
        tail.append(GLYPHS[scaled // denominator])
        carry = scaled % denominator

    if repeat == -1:
        body = "".join(tail)
    else:
        body = "".join(tail[:repeat]) + "[" + "".join(tail[repeat:]) + "]"
    return ("-" if negative else "") + stem + ";" + body
