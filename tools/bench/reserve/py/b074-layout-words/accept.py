from solution import layout_words, line_width

assert layout_words([], 10) == [], "no words lay out as no lines"
assert layout_words(["ab"], 5) == [["ab"]], "one word, one line"
assert layout_words(["ab", "cd", "ef"], 7) == [
    ["ab", "cd"],
    ["ef"],
], "the joining space counts against the width"
assert layout_words(["aa", "bb"], 4) == [
    ["aa"],
    ["bb"],
], "two words needing a space do not share a width-4 line"
assert layout_words(["abcde", "fg"], 5) == [
    ["abcde"],
    ["fg"],
], "a word exactly the column width stands alone"
assert line_width([]) == 0, "an empty line has width zero"
assert line_width(["ab", "c"]) == 4, "helper counts the joining space"


def rejects(*args):
    try:
        layout_words(*args)
    except Exception:
        return True
    return False


assert rejects(["ab"], 0), "zero width is rejected"
assert rejects(["ab"], 6.5), "fractional width is rejected"
assert rejects([""], 5), "empty word is rejected"
assert rejects(["wardrobe"], 5), "word wider than the column is rejected"
print("ok")
