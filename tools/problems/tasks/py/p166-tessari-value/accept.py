from solution import tessari_value

assert tessari_value("K") == 0, "the lone K is nothing"
assert tessari_value("L") == 1, "one"
assert tessari_value("N") == 3, "three"
assert tessari_value("T") == 8, "eight"
assert tessari_value("LK") == 9, "nine"
assert tessari_value("LL") == 10, "ten"
assert tessari_value("MN") == 21, "twenty-one"
assert tessari_value("TT") == 80, "the largest pair"
assert tessari_value("LKK") == 81, "eighty-one"
assert tessari_value("TQL") == 694, "three glyphs"
assert tessari_value("RSTP") == 5017, "four glyphs"


def rejects(text):
    try:
        tessari_value(text)
    except ValueError:
        return True
    return False


assert rejects(""), "empty text rejected"
assert rejects("A"), "foreign glyph rejected"
assert rejects("lm"), "lower case rejected"
assert rejects("KL"), "leading K rejected"
assert rejects("KK"), "doubled K rejected"
assert rejects("L M"), "space rejected"
assert rejects(42), "non-text rejected"
print("ok")
