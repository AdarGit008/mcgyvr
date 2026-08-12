from solution import reflow_text

assert reflow_text("the quick brown fox", 10) == [
    "the quick",
    "brown fox",
], "basic greedy wrap"
assert reflow_text("aaaa bbbbb", 10) == ["aaaa bbbbb"], "exact-width fit"
assert reflow_text("abcdefghij", 10) == ["abcdefghij"], "word at width"
assert reflow_text("a \t b\n c", 10) == ["a b c"], "whitespace collapses"
assert reflow_text("  hi there  ", 8) == ["hi there"], "edges trimmed"
assert reflow_text("", 5) == [], "empty text yields no lines"
assert reflow_text(" \n\t ", 5) == [], "all-whitespace text yields none"
assert reflow_text("one\n\ntwo", 10) == ["one", "", "two"], "paragraph gap"
assert reflow_text("one\n\n\n\ntwo", 10) == ["one", "", "two"], "blank runs, one gap"
assert reflow_text("abcdefghijklm", 5) == [
    "abcde",
    "fghij",
    "klm",
], "long word breaks into pieces"
assert reflow_text("abcdefg hi", 5) == ["abcde", "fg hi"], "words join final piece"
assert reflow_text("abcdefghij x", 5) == [
    "abcde",
    "fghij",
    "x",
], "full final piece takes its line"
assert reflow_text("ab c", 1) == ["a", "b", "c"], "width one splits all"
assert reflow_text("aaa bb", 4) == ["aaa", "bb"], "word moves to next line"


def rejects(text, width):
    try:
        reflow_text(text, width)
    except Exception:
        return True
    return False


assert rejects(42, 10), "non-string text is rejected"
assert rejects("hi", 0), "zero width is rejected"
assert rejects("hi", -3), "negative width is rejected"
assert rejects("hi", 2.5), "fractional width is rejected"
print("ok")
