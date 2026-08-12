from solution import placard_lines

assert placard_lines("hello", 10) == ["hello"], "one word, one line"
assert placard_lines("ab cd", 5) == ["ab cd"], "an exact fit fills the line"
assert placard_lines("ab cd ef", 7) == [
    "ab cd",
    "ef",
], "the joining space counts against the width"
assert placard_lines("the raven flew over the keep", 10) == [
    "the raven",
    "flew over",
    "the keep",
], "greedy fill packs each line"
assert placard_lines("abcd ef", 4) == ["abcd", "ef"], "a full-width word stands alone"
assert placard_lines("one two six", 3) == [
    "one",
    "two",
    "six",
], "narrow placard holds one word per line"


def rejects(text, width):
    try:
        placard_lines(text, width)
    except Exception:
        return True
    return False


assert rejects(42, 10), "non-string text is rejected"
assert rejects("", 10), "empty text is rejected"
assert rejects("hi there", 0), "zero width is rejected"
assert rejects("a  b", 10), "doubled space is rejected"
assert rejects(" a", 10), "leading space is rejected"
assert rejects("abcd", 3), "a word wider than the placard is rejected"
print("ok")
