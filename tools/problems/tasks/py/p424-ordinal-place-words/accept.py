from solution import spell_ordinal_place


def rejects(value):
    try:
        spell_ordinal_place(value)
    except ValueError:
        return True
    return False


assert spell_ordinal_place(1) == "first", "the smallest place"
assert spell_ordinal_place(2) == "second", "two is irregular"
assert spell_ordinal_place(3) == "third", "three is irregular"
assert spell_ordinal_place(4) == "fourth", "four merely takes th"
assert spell_ordinal_place(5) == "fifth", "five is irregular"
assert spell_ordinal_place(8) == "eighth", "eight is irregular"
assert spell_ordinal_place(9) == "ninth", "nine is irregular"
assert spell_ordinal_place(10) == "tenth", "ten merely takes th"
assert spell_ordinal_place(11) == "eleventh", "eleven merely takes th"
assert spell_ordinal_place(12) == "twelfth", "twelve is irregular"
assert spell_ordinal_place(13) == "thirteenth", "a teen takes th"
assert spell_ordinal_place(19) == "nineteenth", "the last teen"
assert spell_ordinal_place(20) == "twentieth", "a round ten trades y for ieth"
assert spell_ordinal_place(21) == "twenty-first", "only the piece past the hyphen changes"
assert spell_ordinal_place(32) == "thirty-second", "a hyphenated compound"
assert spell_ordinal_place(40) == "fortieth", "forty keeps its spelling"
assert spell_ordinal_place(45) == "forty-fifth", "an irregular unit behind a round ten"
assert spell_ordinal_place(99) == "ninety-ninth", "the largest two-figure place"
assert spell_ordinal_place(100) == "one hundredth", "hundred is the trailing piece"
assert spell_ordinal_place(101) == "one hundred and first", "and joins the leftover"
assert spell_ordinal_place(112) == "one hundred and twelfth", "a leftover teen"
assert spell_ordinal_place(120) == "one hundred and twentieth", "a leftover round ten"
assert spell_ordinal_place(203) == "two hundred and third", "a leftover unit"
assert spell_ordinal_place(300) == "three hundredth", "no leftover leaves hundred trailing"
assert spell_ordinal_place(999) == "nine hundred and ninety-ninth", "the largest place"

assert rejects(0), "zero is refused"
assert rejects(1000), "beyond 999 is refused"
assert rejects(-5), "a negative place is refused"
assert rejects(2.5), "a fractional place is refused"
assert rejects("7"), "a string is refused"
print("ok")
