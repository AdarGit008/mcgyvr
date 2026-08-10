from solution import lift_distance, run_lift, split_calls, sweep_report

assert run_lift(5, []) == [], "no calls yields no stops"
assert run_lift(4, [[4, "up"], [6, "up"]]) == [
    4,
    6,
], "an up call at the boarding floor is served first"
assert run_lift(5, [[2, "up"], [8, "up"], [6, "down"], [1, "down"], [5, "up"]]) == [
    5,
    8,
    6,
    1,
    2,
], "up sweep, then down sweep, then the up calls left behind"
assert run_lift(0, [[3, "down"], [9, "down"], [6, "down"]]) == [
    9,
    6,
    3,
], "the down sweep runs highest floor first"
assert run_lift(10, [[2, "up"], [7, "down"]]) == [
    7,
    2,
], "a behind up call waits until the down sweep is done"
assert run_lift(1, [[4, "up"], [4, "up"]]) == [4], "repeated calls collapse"
assert run_lift(1, [[4, "up"], [4, "down"]]) == [
    4,
    4,
], "both directions at one floor are two stops"
assert run_lift(4, [[4, "down"]]) == [
    4
], "a down call at the boarding floor is served on the down sweep"
assert run_lift(9, [[3, "up"], [5, "up"]]) == [3, 5], "behind up calls run ascending"
assert run_lift(
    6,
    [
        [6, "up"],
        [11, "up"],
        [2, "up"],
        [9, "down"],
        [4, "down"],
        [10, "up"],
        [4, "down"],
    ],
) == [6, 10, 11, 9, 4, 2], "a full mixed sweep over all three phases"
assert split_calls(5, [[7, "up"], [2, "up"], [5, "up"], [8, "down"], [3, "down"]]) == {
    "up_ahead": [5, 7],
    "up_behind": [2],
    "down": [3, 8],
}, "split_calls sorts each part ascending"
assert split_calls(4, []) == {
    "up_ahead": [],
    "up_behind": [],
    "down": [],
}, "split_calls of no calls is three empty parts"
assert lift_distance(5, []) == 0, "no stops means no travel"
assert lift_distance(5, [8, 3, 6]) == 11, "travel sums each leg"
assert sweep_report(3, []) == {
    "stops": [],
    "travelled": 0,
    "reversals": 0,
}, "an idle sweep reports zeros"
assert sweep_report(5, [[8, "up"], [2, "down"]]) == {
    "stops": [8, 2],
    "travelled": 9,
    "reversals": 1,
}, "one reversal turning from up to down"
assert sweep_report(4, [[4, "up"], [6, "up"], [1, "down"]]) == {
    "stops": [4, 6, 1],
    "travelled": 7,
    "reversals": 1,
}, "a zero-length move counts no reversal"


def rejects(fn, *args):
    try:
        fn(*args)
    except ValueError:
        return True
    return False


assert rejects(run_lift, "x", []), "non-integer boarding floor"
assert rejects(run_lift, 1, "x"), "non-list calls"
assert rejects(run_lift, 1, [[2]]), "a one-item call"
assert rejects(run_lift, 1, [[2.5, "up"]]), "a fractional floor"
assert rejects(run_lift, 1, [[2, "sideways"]]), "a bad direction"
assert rejects(lift_distance, 1, [2.5]), "a fractional stop"
assert rejects(lift_distance, 1, "x"), "non-list stops"
print("ok")
