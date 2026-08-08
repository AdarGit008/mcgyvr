from solution import fold_visit_trail

assert fold_visit_trail([], 5) == [], "no pings leave no trail"
assert fold_visit_trail([["ida", 10]], 5) == [
    ["ida", [1]]
], "a single ping is a run of one"
assert fold_visit_trail([["ida", 30], ["ida", 10], ["ida", 12]], 5) == [
    ["ida", [2, 1]]
], "the stamps are put in order before the runs are cut"
assert fold_visit_trail([["ida", 0], ["ida", 5]], 5) == [
    ["ida", [1, 1]]
], "a distance of exactly idle breaks the run"
assert fold_visit_trail([["ida", 0], ["ida", 4]], 5) == [
    ["ida", [2]]
], "one short of idle keeps the run going"
assert fold_visit_trail(
    [["jib", 100], ["ida", 0], ["ida", 4], ["jib", 90]], 5
) == [["ida", [2]], ["jib", [1, 1]]], "handles are answered in rising order"
assert fold_visit_trail([["ida", 3], ["ida", 1], ["ida", 2]], 1) == [
    ["ida", [1, 1, 1]]
], "an idle of one breaks between every distinct stamp"
assert fold_visit_trail(
    [["ida", 8], ["ida", 0], ["ida", 2], ["ida", 20], ["ida", 9]], 5
) == [["ida", [2, 2, 1]]], "three runs out of five scattered pings"


def rejects(pings, idle):
    try:
        fold_visit_trail(pings, idle)
    except ValueError:
        return True
    return False


assert rejects("pings", 5), "a non-list is rejected"
assert rejects([["ida", 1, 2]], 5), "a ping of three items is rejected"
assert rejects([["", 1]], 5), "an empty handle is rejected"
assert rejects([["ida", "soon"]], 5), "a stamp that is not a number is rejected"
assert rejects([["ida", 7], ["ida", 7]], 5), "one handle carrying a stamp twice is rejected"
assert rejects([["ida", 1]], 0), "an idle of zero is rejected"
assert rejects([["ida", 1]], 2.5), "a fractional idle is rejected"
print("ok")
