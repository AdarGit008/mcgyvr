from solution import nest_outline

assert nest_outline("solo") == [["solo", []]], "one line, one item"
assert nest_outline("a\nb") == [["a", []], ["b", []]], "two level-zero items"
assert nest_outline("a\n  b\n    c") == [
    ["a", [["b", [["c", []]]]]]
], "a straight descent nests three deep"
assert nest_outline("root\n  kid\n    grand\n  kid2\nsecond\n  x") == [
    ["root", [["kid", [["grand", []]]], ["kid2", []]]],
    ["second", [["x", []]]],
], "siblings after a dedent attach to the right parent"
assert nest_outline("a\n  b\n    c\nd") == [
    ["a", [["b", [["c", []]]]]],
    ["d", []],
], "a dedent may drop several levels at once"
assert nest_outline("top item\n  sub item") == [
    ["top item", [["sub item", []]]]
], "internal spaces in the text survive"
assert nest_outline("a\n  b\n") == [
    ["a", [["b", []]]]
], "a single final newline is tolerated"


def rejects(value):
    try:
        nest_outline(value)
    except ValueError:
        return True
    return False


assert rejects(""), "empty input"
assert rejects("a\n\tb"), "tab character"
assert rejects(" a"), "odd indentation"
assert rejects("  a"), "opening line indented"
assert rejects("a\n    b"), "two-level jump"
assert rejects("a\n\nb"), "blank line inside"
assert rejects("a\n  "), "all-space line"
print("ok")
