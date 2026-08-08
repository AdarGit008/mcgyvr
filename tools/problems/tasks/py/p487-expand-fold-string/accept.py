from solution import expand_fold_string

assert expand_fold_string("an(t(-|e)|vil)|bee") == [
    "ant",
    "ante",
    "anvil",
    "bee",
], "a nested bracket unpacks without being torn apart"
assert expand_fold_string("ca(r(-|d|e)|t)") == [
    "car",
    "card",
    "care",
    "cat",
], "a hyphen among the branches yields the bare stem"
assert expand_fold_string("a") == ["a"], "a bare stem unpacks to itself"
assert expand_fold_string("a|b|z") == [
    "a",
    "b",
    "z",
], "branches come back in the order they stand"
assert expand_fold_string("a(-|b)") == ["a", "ab"], "the hyphen comes first here"
assert expand_fold_string("d(o(-|g|t|ze)|ust)") == [
    "do",
    "dog",
    "dot",
    "doze",
    "dust",
], "two levels of bracket unpack in the enclosed order"
assert expand_fold_string("ox(-|en|ide)|pea(-|r|t)") == [
    "ox",
    "oxen",
    "oxide",
    "pea",
    "pear",
    "peat",
], "two bracketed branches side by side"
assert expand_fold_string("mist(-|er|le|y)") == [
    "mist",
    "mister",
    "mistle",
    "misty",
], "one stem with four endings"


def rejects(line):
    try:
        expand_fold_string(line)
    except ValueError:
        return True
    return False


assert rejects(""), "an empty line is rejected"
assert rejects(7), "a line must be a string"
assert rejects("A(b)"), "a capital letter is rejected"
assert rejects("a b"), "a blank is rejected"
assert rejects("-"), "a hyphen alone at the top is rejected"
assert rejects("a|-"), "a hyphen outside a bracket is rejected"
assert rejects("a(-x)"), "a hyphen must stand alone"
assert rejects("a||b"), "an empty branch is rejected"
assert rejects("|a"), "a leading bar is rejected"
assert rejects("a|"), "a trailing bar is rejected"
assert rejects("(a|b)"), "a bracket with no stem is rejected"
assert rejects("a()"), "an empty bracket is rejected"
assert rejects("a(b"), "an unclosed bracket is rejected"
assert rejects("a(b))"), "a spare closing bracket is rejected"
assert rejects("a(b)c"), "text after a bracket is rejected"
assert rejects("a-b"), "a hyphen mid-stem is rejected"
print("ok")
