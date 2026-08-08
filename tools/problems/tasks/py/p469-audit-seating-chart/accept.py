from solution import audit_seating_chart

CHART = [["ana", "ben", ""], ["cal", "", "dot"]]

assert audit_seating_chart(
    CHART, [["ana", "ben"], ["ben", "dot"]], [["ana", "cal"], ["cal", "dot"]]
) == [
    "split:ben-dot",
    "touching:ana-cal",
], "wanted ties come first, then the banned ones"

assert (
    audit_seating_chart(CHART, [["ana", "ben"]], [["cal", "dot"]]) == []
), "a chart that breaks nothing puts out nothing"

assert audit_seating_chart(CHART, [["dot", "ben"]], []) == [
    "split:ben-dot"
], "the names are joined with the earlier one alphabetically first"

assert (
    audit_seating_chart(CHART, [["ana", "cal"]], []) == []
), "sitting one band apart in the same column counts as next to"

assert audit_seating_chart(CHART, [["ana", "dot"]], [["ana", "dot"]]) == [
    "split:ana-dot"
], "cells meeting only at a corner are not next to one another"

assert (
    audit_seating_chart([["one", "", "two"]], [], [["one", "two"]]) == []
), "a blank place between two names keeps them apart"

assert audit_seating_chart(
    [["p", "q"], ["r", "s"]],
    [["p", "s"], ["q", "r"]],
    [["p", "q"], ["r", "s"], ["p", "r"]],
) == [
    "split:p-s",
    "split:q-r",
    "touching:p-q",
    "touching:r-s",
    "touching:p-r",
], "every finding is reported, each list in its own order"


def rejects(chart, glued, split):
    try:
        audit_seating_chart(chart, glued, split)
    except ValueError:
        return True
    return False


assert rejects([], [], []), "an empty chart"
assert rejects([["a", "b"], ["c"]], [], []), "bands of differing length are rejected"
assert rejects([["a", 7]], [], []), "a cell that is not a string is rejected"
assert rejects([["a", "a"]], [], []), "a name written twice is rejected"
assert rejects(
    [["a", "b"]], [["a", "zz"]], []
), "a tie naming somebody absent is rejected"
assert rejects(
    [["a", "b"]], [["a", "a"]], []
), "a tie naming one person twice is rejected"
assert rejects([["a", "b"]], [["a", "b", "c"]], []), "a tie of three names is rejected"
assert rejects(
    [["a", "b"]], "nope", []
), "a list of ties that is not a list is rejected"
print("ok")
