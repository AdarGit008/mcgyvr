from solution import label_cadence_walk

assert label_cadence_walk(
    [["s", "a", "red"], ["a", "g", "blue"]], ["red", "blue"], "s", "g"
) == 2, "a two-edge walk matches the cadence once"
assert label_cadence_walk(
    [["s", "a", "r"], ["a", "b", "b"], ["b", "g", "r"]], ["r", "b"], "s", "g"
) == 3, "the cadence wraps around past its last label"
assert label_cadence_walk(
    [["s", "a", "r"], ["a", "s", "b"], ["s", "a", "g"], ["a", "g", "r"]],
    ["r", "b", "g"],
    "s",
    "g",
) == 4, "the walk may pass through a node twice at different cadence positions"
assert label_cadence_walk(
    [["s", "a", "r"], ["a", "g", "b"]], ["r", "b", "g"], "s", "g"
) == 2, "the walk may end before the cadence completes a lap"
assert label_cadence_walk(
    [["s", "a", "b"]], ["r"], "s", "a"
) == -1, "no edge carries the opening label"
assert label_cadence_walk(
    [["s", "a", "r"]], ["r"], "s", "s"
) == 0, "equal endpoints walk nowhere"


def rejects(edges, cadence, start, goal):
    try:
        label_cadence_walk(edges, cadence, start, goal)
    except ValueError:
        return True
    return False


assert rejects([["s", "a", "r"]], [], "s", "a"), "an empty cadence is rejected"
assert rejects([["s", "a", "r"]], ["r", ""], "s", "a"), "an empty cadence entry is rejected"
assert rejects([["s", "a"]], ["r"], "s", "a"), "a two-part edge is rejected"
assert rejects([["s", "a", ""]], ["r"], "s", "a"), "an empty edge label is rejected"
assert rejects([["s", "a", "r"]], ["r"], "z", "a"), "an unknown start is rejected"
assert rejects([["s", "a", "r"]], ["r"], "s", "z"), "an unknown goal is rejected"
print("ok")
