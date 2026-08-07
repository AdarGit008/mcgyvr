from solution import write_picket_strip


def rejects(digits):
    try:
        write_picket_strip(digits)
    except ValueError:
        return True
    return False


assert write_picket_strip("0") == {"strip": "nnwwnnnwn", "width": 12}, (
    "zero is the first two bars wide"
)
assert write_picket_strip("9") == {"strip": "nnnnnwwwn", "width": 12}, (
    "nine is the last two bars wide"
)
assert write_picket_strip("4") == {"strip": "nnnwwnnwn", "width": 12}, (
    "four opens the second block of choices"
)
assert write_picket_strip("07") == {"strip": "nnwwnnnnnwwnwn", "width": 19}, (
    "two digits stand between the guards"
)
assert write_picket_strip("555") == {"strip": "nnnwnwnnwnwnnwnwnwn", "width": 26}, (
    "a digit repeats its own five bars"
)
assert write_picket_strip("0123456789") == {
    "strip": "nnwwnnnwnwnnwnnwnwnnnwnwwnnnwnwnnwnnwnnwwnnnwnwnnnwwwn",
    "width": 75,
}, "every digit in order"

one = write_picket_strip("6")
assert one["strip"][:2] == "nn", "the head guard is two narrow bars"
assert one["strip"][-2:] == "wn", "the tail guard is wide then narrow"
assert len(one["strip"]) == 9, "one digit makes nine bars in all"
assert one["strip"][2:7].count("w") == 2, "a digit is drawn with exactly two wide bars"

assert rejects(7), "a number is no digit string"
assert rejects(""), "an empty string is rejected"
assert rejects("12a"), "a letter is rejected"
assert rejects("1 2"), "a space is rejected"
assert rejects("-4"), "a sign is rejected"
print("ok")
