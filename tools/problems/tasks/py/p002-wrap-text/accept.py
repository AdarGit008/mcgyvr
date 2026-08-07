from solution import wrap_text

assert wrap_text("the quick brown fox jumps", 10) == [
    "the quick",
    "brown fox",
    "jumps",
], "greedy fill"
assert wrap_text("a bb ccc", 3) == ["a", "bb", "ccc"], "narrow lines"
assert wrap_text("one", 80) == ["one"], "single word fits"
assert wrap_text("hi extraordinary yo", 5) == [
    "hi",
    "extraordinary",
    "yo",
], "oversized word gets its own line"
assert wrap_text("ab cd", 5) == ["ab cd"], "exact width fits"
assert wrap_text("ab cd", 4) == ["ab", "cd"], "one short of fitting splits"


def rejects(*args):
    try:
        wrap_text(*args)
    except ValueError:
        return True
    return False


assert rejects("ok", 0), "zero width is rejected"
assert rejects("ok", 2.5), "fractional width is rejected"
assert rejects(" lead", 10), "leading space is rejected"
assert rejects("trail ", 10), "trailing space is rejected"
assert rejects("a  b", 10), "doubled space is rejected"
assert rejects(42, 10), "non-string text is rejected"
print("ok")
