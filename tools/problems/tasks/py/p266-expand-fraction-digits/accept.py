from solution import expand_fraction_digits

assert expand_fraction_digits(1, 6, 10) == "0;1[6]", "one settled glyph then a recurring one"
assert expand_fraction_digits(1, 7, 10) == "0;[142857]", "the whole tail recurs from the start"
assert expand_fraction_digits(3, 2, 10) == "1;5", "a settling tail carries no brackets"
assert expand_fraction_digits(5, 1, 10) == "5", "an exact whole drops the semicolon entirely"
assert expand_fraction_digits(0, 9, 10) == "0", "nothing is written as a bare zero"
assert expand_fraction_digits(-1, 3, 10) == "-0;[3]", "the minus survives a zero stem"
assert expand_fraction_digits(-22, 7, 10) == "-3;[142857]", "a negative mixed quantity"
assert expand_fraction_digits(-4, 2, 10) == "-2", "a negative exact whole"
assert expand_fraction_digits(1, 2, 3) == "0;[1]", "a half recurs in base three"
assert expand_fraction_digits(1, 3, 3) == "0;1", "a third settles in base three"
assert expand_fraction_digits(1, 9, 3) == "0;01", "a leading zero glyph in the tail"
assert expand_fraction_digits(1, 5, 12) == "0;[2497]", "a four glyph cycle in base twelve"
assert expand_fraction_digits(1, 8, 12) == "0;16", "a settling tail in base twelve"
assert expand_fraction_digits(255, 16, 16) == "F;F", "letter glyphs on both sides of the semicolon"
assert expand_fraction_digits(1, 40, 20) == "0;0A", "a letter glyph after a zero glyph"
assert expand_fraction_digits(121, 11, 11) == "10", "a stem needing two glyphs"
assert expand_fraction_digits(100, 3, 10) == "33;[3]", "a two glyph stem beside a cycle"
assert expand_fraction_digits(1, 64, 4) == "0;001", "two zero glyphs before the tail settles"
assert expand_fraction_digits(1, 11, 10) == "0;[09]", "a cycle opening on a zero glyph"


def rejects(numerator, denominator, base):
    try:
        expand_fraction_digits(numerator, denominator, base)
    except ValueError:
        return True
    return False


assert rejects(1, 6, 2), "a base under three"
assert rejects(1, 6, 21), "a base over twenty"
assert rejects(1, 0, 10), "a denominator of zero"
assert rejects(1, -3, 10), "a negative denominator"
assert rejects(1.5, 6, 10), "a fractional numerator"
assert rejects(1, 6, 10.5), "a fractional base"
assert rejects(1000001, 6, 10), "a numerator past the ceiling"
assert rejects(1, 1000001, 10), "a denominator past the ceiling"
assert rejects("1", 6, 10), "a numerator that is text"
print("ok")
