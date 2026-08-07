from solution import span_conflicts

assert span_conflicts([]) == [], "no annotations"
assert (
    span_conflicts([[0, 4, "loc"], [4, 8, "org"]]) == []
), "touching annotations with different labels never conflict"
assert span_conflicts([[0, 5, "loc"], [3, 8, "org"]]) == [
    [0, 1]
], "overlap across labels is a conflict"
assert (
    span_conflicts([[0, 5, "loc"], [3, 8, "loc"]]) == []
), "same-label overlap is layering, not a conflict"
assert span_conflicts([[2, 9, "a"], [3, 5, "b"]]) == [
    [0, 1]
], "containment across labels is a conflict"
assert span_conflicts([[0, 10, "a"], [1, 3, "b"], [5, 7, "c"], [12, 14, "b"]]) == [
    [0, 1],
    [0, 2],
], "pairs use original indices in lexicographic order"
assert span_conflicts([[6, 8, "x"], [0, 7, "y"], [7, 9, "y"]]) == [
    [0, 1],
    [0, 2],
], "an unsorted input still reports i below j"


def rejects(spans):
    try:
        span_conflicts(spans)
    except ValueError:
        return True
    return False


assert rejects([[5, 5, "a"]]), "empty span is rejected"
assert rejects([[1.5, 3, "a"]]), "non-integer bound is rejected"
assert rejects([[0, 3, ""]]), "empty label is rejected"
print("ok")
