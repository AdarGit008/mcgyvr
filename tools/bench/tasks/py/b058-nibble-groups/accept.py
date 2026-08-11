from solution import format_bits

assert format_bits(0, 4) == "0000", "zero pads to the full width"
assert format_bits(5, 4) == "0101", "a single nibble renders directly"
assert format_bits(300, 12) == "0001 0010 1100", "wider values group in fours"
assert format_bits(255, 8) == "1111 1111", "a saturated byte is all ones"
assert format_bits(1, 32) == (
    "0000 0000 0000 0000 0000 0000 0000 0001"
), "the widest allowed width still renders"


def rejects(*args):
    try:
        format_bits(*args)
    except ValueError:
        return True
    return False


assert rejects(16, 4), "a value too wide for the width is rejected"
assert rejects(5, 10), "a width off the nibble grid is rejected"
assert rejects(1, 36), "a width beyond 32 bits is rejected"
assert rejects(-3, 8), "a negative value is rejected"
print("ok")
