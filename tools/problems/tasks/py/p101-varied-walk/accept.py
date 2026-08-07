from solution import varied_label_walk

assert varied_label_walk(
    [["s", "a", "x"], ["a", "g", "y"]], "s", "g"
) == 2, "two differently labeled edges chain"
assert varied_label_walk(
    [["s", "a", "x"], ["a", "g", "x"]], "s", "g"
) == -1, "a repeated label in a row is forbidden"
assert varied_label_walk(
    [["s", "a", "r"], ["a", "g", "r"], ["a", "b", "g"], ["b", "a", "b"]], "s", "g"
) == 4, "the only lawful walk leaves a and comes back under another label"
assert varied_label_walk(
    [["s", "a", "x"], ["s", "a", "y"], ["a", "g", "x"]], "s", "g"
) == 2, "parallel edges with different labels are distinct arrivals"
assert varied_label_walk(
    [["s", "a", "x"], ["a", "g", "y"], ["s", "g", "z"]], "s", "g"
) == 1, "a direct edge wins"
assert varied_label_walk([["s", "a", "x"]], "s", "s") == 0, "equal endpoints need no walk"
assert varied_label_walk(
    [["s", "a", "x"], ["g", "b", "y"]], "s", "g"
) == -1, "a goal with no way in stays unreached"


def rejects(edges, start, goal):
    try:
        varied_label_walk(edges, start, goal)
    except ValueError:
        return True
    return False


assert rejects([["s", "a"]], "s", "a"), "a two-part edge is rejected"
assert rejects([["s", "a", ""]], "s", "a"), "an empty label is rejected"
assert rejects([["s", "a", "x"]], "z", "a"), "an unknown start is rejected"
assert rejects([["s", "a", "x"]], "s", "z"), "an unknown goal is rejected"
print("ok")
