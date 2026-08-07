from solution import fit_tag_lines


def lines(*rows):
    return "\n".join(rows)


box = {"head": "box", "items": ["red", {"head": "tin", "items": ["a", "b"]}]}
row = {"head": "row", "items": ["one", "two"]}
deep = {"head": "a", "items": [{"head": "b", "items": ["c"]}]}

assert fit_tag_lines(box, 19) == "box(red, tin(a, b))", (
    "a tight form measuring exactly the width stays on one line"
)
assert fit_tag_lines(box, 18) == lines("box(", "  red,", "  tin(a, b)", ")"), (
    "one character over the width spreads the outer tag only"
)
assert fit_tag_lines(box, 10) == lines(
    "box(", "  red,", "  tin(", "    a,", "    b", "  )", ")"
), "the inner tag spreads once its own opening spaces are counted"
assert fit_tag_lines(row, 13) == "row(one, two)", (
    "items are parted by a comma and a space"
)
assert fit_tag_lines(row, 12) == lines("row(", "  one,", "  two", ")"), (
    "the last item carries no comma"
)
assert fit_tag_lines(deep, 7) == "a(b(c))", "a tag nested tight enough fits"
assert fit_tag_lines(deep, 6) == lines("a(", "  b(c)", ")"), (
    "a child that still fits at its own depth is left tight"
)
assert fit_tag_lines(deep, 5) == lines("a(", "  b(", "    c", "  )", ")"), (
    "two spaces of depth are enough to push the child over"
)
assert fit_tag_lines({"head": "nil", "items": []}, 5) == "nil()", (
    "a tag with no items is an empty pair of brackets"
)
assert fit_tag_lines({"head": "q", "items": ["abcdefghij"]}, 3) == lines(
    "q(", "  abcdefghij", ")"
), "a word longer than the width is never spread"


def rejects(one, two):
    try:
        fit_tag_lines(one, two)
    except ValueError:
        return True
    return False


assert rejects("red", 10), "a bare word is rejected"
assert rejects({"head": "Box", "items": []}, 10), "a head with a capital is rejected"
assert rejects({"head": "", "items": []}, 10), "an empty head is rejected"
assert rejects({"head": "box"}, 10), "a tag without items is rejected"
assert rejects({"head": "box", "items": "red"}, 10), (
    "items given as a string is rejected"
)
assert rejects({"head": "box", "items": [7]}, 10), (
    "an item that is a number is rejected"
)
assert rejects({"head": "box", "items": [""]}, 10), "an empty word is rejected"
assert rejects({"head": "box", "items": [{"head": "Bad", "items": []}]}, 10), (
    "a bad head deeper down is rejected too"
)
assert rejects(row, 0), "a width of zero is rejected"
assert rejects(row, 1.5), "a fractional width is rejected"
assert rejects(row, "10"), "a width given as a string is rejected"
assert rejects(row, True), "a width given as a boolean is rejected"
print("ok")
