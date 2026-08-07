from solution import grade_containment

assert (
    grade_containment(["the", "cat", "sat", "on", "the", "mat"], ["the", "cat", "sat"], 2)
    == 1000
), "every draft stretch is present"
assert (
    grade_containment(["a", "b", "a", "b"], ["a", "b", "a", "b", "a", "b"], 2) == 600
), "copies run out"
assert grade_containment(["x", "y"], ["x", "y", "z", "w"], 2) == 333, "one of three"
assert (
    grade_containment(["m", "n"], ["p", "q", "m", "n"], 2) == 333
), "the closing stretch counts"
assert grade_containment([], ["a", "b"], 2) == 0, "an empty source grades nought"
assert (
    grade_containment(["red", "blue"], ["red", "red", "blue"], 1) == 666
), "single words, one repeat unspent"
assert (
    grade_containment(["a", "b", "c", "d"], ["a", "b", "c"], 3) == 1000
), "stretches of three"
assert grade_containment(["q", "r", "s"], ["t", "u", "v"], 2) == 0, "nothing carried"


def rejects(source, draft, span):
    try:
        grade_containment(source, draft, span)
    except ValueError:
        return True
    return False


assert rejects(["a", "b"], ["a", "b"], 0), "span nought is rejected"
assert rejects(["a", "b"], ["a", "b"], 1.5), "a fractional span is rejected"
assert rejects("ab", ["a", "b"], 2), "a source that is not a list is rejected"
assert rejects(["a", 5], ["a", "b"], 2), "a non-word element is rejected"
assert rejects(["a", "b"], ["a", ""], 2), "an empty word is rejected"
assert rejects(["a", "b", "c"], ["a", "b"], 3), "a short draft is rejected"
print("ok")
