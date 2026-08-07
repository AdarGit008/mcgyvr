from solution import order_sections

assert order_sections(["10", "9", "1"]) == ["1", "9", "10"], (
    "components compare numerically, not lexicographically"
)
assert order_sections(["1.2.10", "1.2.9", "1.2.2"]) == [
    "1.2.2",
    "1.2.9",
    "1.2.10",
], "deep components compare numerically too"
assert order_sections(["2.1", "2", "2.1.1"]) == [
    "2",
    "2.1",
    "2.1.1",
], "a prefix label precedes its extensions"
assert order_sections(["3.2", "1.10", "3", "1.9", "2"]) == [
    "1.9",
    "1.10",
    "2",
    "3",
    "3.2",
], "a mixed bag sorts like a table of contents"
assert order_sections(["0", "0.1", "1"]) == [
    "0",
    "0.1",
    "1",
], "a lone zero component is legal"
assert order_sections([]) == [], "no labels, no output"
assert order_sections(["7"]) == ["7"], "a single label survives alone"


def rejects(labels):
    try:
        order_sections(labels)
    except ValueError:
        return True
    return False


assert rejects(["1.1", "1.1"]), "a duplicate label is rejected"
assert rejects(["2.01"]), "a zero-padded component is rejected"
assert rejects(["1..2"]), "an empty component is rejected"
assert rejects(["1.2."]), "a trailing dot is rejected"
assert rejects([""]), "the empty label is rejected"
assert rejects([3]), "a non-string label is rejected"
print("ok")
