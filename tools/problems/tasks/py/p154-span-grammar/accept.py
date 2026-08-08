from solution import expand_span_grammar

assert expand_span_grammar("img<1..3>.png") == [
    "img1.png",
    "img2.png",
    "img3.png",
], "a span counts through its range"
assert expand_span_grammar("<08..11>") == [
    "08",
    "09",
    "10",
    "11",
], "padding follows the width of the first endpoint"
assert expand_span_grammar("<9..11>") == [
    "10",
    "11",
    "9",
], "sort is by code point, not numeric"
assert expand_span_grammar("<b|a>-<1..2>") == [
    "a-1",
    "a-2",
    "b-1",
    "b-2",
], "groups combine as a cartesian product, then sort"
assert expand_span_grammar("~<a~|b~>") == [
    "<a|b>"
], "tilde makes the grammar characters literal"
assert expand_span_grammar("<x|x>") == ["x"], "duplicates collapse"
assert expand_span_grammar("plain") == [
    "plain"
], "a groupless pattern stands for itself"


def rejects(value):
    try:
        expand_span_grammar(value)
    except ValueError:
        return True
    return False


assert rejects("<a"), "unclosed group is rejected"
assert rejects("a>b"), "stray close is rejected"
assert rejects("<a||b>"), "empty choice is rejected"
assert rejects("<5..3>"), "descending span is rejected"
assert rejects("<1..600>"), "oversized span is rejected"
assert rejects("<a|b><1..300>"), "oversized product is rejected"
assert rejects("~x"), "bad escape is rejected"
assert rejects("<a.b>"), "choice with punctuation is rejected"
assert rejects(42), "non-string is rejected"
print("ok")
