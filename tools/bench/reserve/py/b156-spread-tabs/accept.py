from solution import spread_tabs

assert spread_tabs("plain text", 4) == "plain text", "text without tabs is unchanged"
assert spread_tabs("", 4) == "", "empty text is unchanged"
assert spread_tabs("\tx", 4) == "    x", "a leading tab reaches the first stop"
assert spread_tabs("a\tb", 4) == "a   b", "a tab pads to the next stop"
assert spread_tabs("abcd\tz", 4) == "abcd    z", "a tab on a stop jumps a full width"
assert spread_tabs("\t\tx", 2) == "    x", "consecutive tabs each reach their own stop"
assert spread_tabs("ab\n\tz", 4) == "ab\n    z", "a newline returns the column to zero"
assert spread_tabs("a\tb", 1) == "a b", "width one pads a single space"


def rejects(*args):
    try:
        spread_tabs(*args)
    except ValueError:
        return True
    return False


assert rejects(42, 4), "non-string text is rejected"
assert rejects("a\tb", 0), "zero width is rejected"
assert rejects("a\tb", 2.5), "fractional width is rejected"
assert rejects("a\tb", "4"), "non-number width is rejected"
print("ok")
