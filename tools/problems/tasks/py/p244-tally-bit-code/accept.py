from solution import build_weight_code

assert build_weight_code([["zed", 7]]) == {
    "codes": {"zed": "0"},
    "bits": 7,
    "tallest": 1,
}, "a lone token takes the bits 0"
assert build_weight_code([["b", 1], ["a", 1]]) == {
    "codes": {"a": "0", "b": "1"},
    "bits": 2,
    "tallest": 1,
}, "two tokens of equal tally go by letter order"
assert build_weight_code([["a", 5], ["b", 2], ["c", 1], ["d", 1]]) == {
    "codes": {"a": "1", "b": "00", "c": "010", "d": "011"},
    "bits": 15,
    "tallest": 3,
}, "a lopsided tally makes a lopsided walk"
assert build_weight_code([["s", 1], ["r", 1], ["q", 1], ["p", 1]]) == {
    "codes": {"p": "00", "q": "01", "r": "10", "s": "11"},
    "bits": 8,
    "tallest": 2,
}, "four equal tallies give four bits of two"
assert build_weight_code([["x", 1], ["y", 1], ["z", 2]]) == {
    "codes": {"x": "10", "y": "11", "z": "0"},
    "bits": 6,
    "tallest": 2,
}, "a leaf bud outranks a fresh bud of the same load"
assert build_weight_code([["m", 3], ["n", 3], ["o", 3]]) == {
    "codes": {"m": "10", "n": "11", "o": "0"},
    "bits": 15,
    "tallest": 2,
}, "three equal tallies leave the last token shortest"
assert build_weight_code([["ab", 2], ["b", 3]]) == {
    "codes": {"ab": "0", "b": "1"},
    "bits": 5,
    "tallest": 1,
}, "multi-letter tokens sort as words"


def rejects(value):
    try:
        build_weight_code(value)
    except ValueError:
        return True
    return False


assert rejects("abc"), "a non-list argument is rejected"
assert rejects([]), "an empty entry list is rejected"
assert rejects([["a"]]), "an entry of one thing is rejected"
assert rejects([["A", 1]]), "a capital token is rejected"
assert rejects([["", 1]]), "an empty token is rejected"
assert rejects([["a", 1], ["a", 2]]), "a repeated token is rejected"
assert rejects([["a", 0]]), "a tally of zero is rejected"
assert rejects([["a", 1.5]]), "a fractional tally is rejected"
print("ok")
