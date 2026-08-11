from solution import bracket_depth


def rejects(text):
    try:
        bracket_depth(text)
    except Exception:
        return True
    return False


assert bracket_depth("a(b)c") == 1, "one bracket nests once"
assert bracket_depth("((x))") == 2, "two brackets nest twice"
assert bracket_depth("(a)(b)") == 1, "side by side does not deepen"
assert bracket_depth("(()(()))") == 3, "the deepest run is reported"
assert bracket_depth("plain") == 0, "a text with no brackets"
assert bracket_depth("") == 0, "an empty text"
assert rejects(")("), "a close before an open is rejected"
assert rejects("(("), "a bracket left open is rejected"
print("ok")
