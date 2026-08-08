from solution import sweep_probe_scales


def deck(channel, ladder, bias):
    return {"channel": channel, "ladder": ladder, "bias": bias}


def took(channel, count):
    return {"channel": channel, "count": count}


assert sweep_probe_scales(
    [
        deck("heat", [[0, 0], [100, 1000]], 0),
        deck("cold", [[-50, 20], [50, -20]], 5),
    ],
    [
        took("heat", 50),
        took("heat", -10),
        took("heat", 250),
        took("cold", 0),
        took("cold", 25),
        took("heat", 3),
    ],
) == {
    "readings": ["heat 500", "heat 0", "heat 1000", "cold 5", "cold -5", "heat 30"],
    "low": 1,
    "high": 1,
    "span": ["heat 0 1000", "cold -5 5"],
}, "two channels, both pins, and a bias on a falling ladder"

assert sweep_probe_scales(
    [deck("tilt", [[0, 0], [3, 1]], 0)], [took("tilt", 1), took("tilt", 2)]
) == {
    "readings": ["tilt 0", "tilt 1"],
    "low": 0,
    "high": 0,
    "span": ["tilt 0 1"],
}, "a third settles down and two thirds settles up"

assert sweep_probe_scales(
    [deck("up", [[0, 0], [2, 1]], 0), deck("down", [[0, 0], [2, -1]], 0)],
    [took("up", 1), took("down", 1)],
) == {
    "readings": ["up 1", "down -1"],
    "low": 0,
    "high": 0,
    "span": ["up 1 1", "down -1 -1"],
}, "a half settles away from nought on either side"

assert sweep_probe_scales(
    [deck("idle", [[0, 5], [10, 5]], 0), deck("busy", [[0, 0], [10, 100]], -3)],
    [took("busy", 5)],
) == {
    "readings": ["busy 47"],
    "low": 0,
    "high": 0,
    "span": ["busy 47 47"],
}, "a channel no sample named is left out of the span"

assert sweep_probe_scales(
    [deck("pin", [[2, 7], [8, 7]], -7)], [took("pin", 0), took("pin", 99)]
) == {
    "readings": ["pin 0", "pin 0"],
    "low": 1,
    "high": 1,
    "span": ["pin 0 0"],
}, "the bias applies to a pinned figure too"

assert sweep_probe_scales(
    [deck("edge", [[4, 9], [12, 21]], 0)], [took("edge", 4), took("edge", 12)]
) == {
    "readings": ["edge 9", "edge 21"],
    "low": 0,
    "high": 0,
    "span": ["edge 9 21"],
}, "a count sitting exactly on an end rung is no pin at all"

assert sweep_probe_scales([deck("quiet", [[0, 0], [5, 5]], 0)], []) == {
    "readings": [],
    "low": 0,
    "high": 0,
    "span": [],
}, "no samples leaves every tally at nought"

assert sweep_probe_scales(
    [deck("bend", [[0, 0], [4, 40], [10, 10]], 0)], [took("bend", 2), took("bend", 7)]
) == {
    "readings": ["bend 20", "bend 25"],
    "low": 0,
    "high": 0,
    "span": ["bend 20 25"],
}, "the rising rung and the falling rung are told apart"


def rejects(*args):
    try:
        sweep_probe_scales(*args)
    except ValueError:
        return True
    return False


assert rejects("no", []), "channels must be a list"
assert rejects([4], []), "a channel must be a record"
assert rejects([{"channel": "a", "ladder": [[0, 0], [1, 1]]}], []), "a missing channel key is refused"
assert rejects([deck("", [[0, 0], [1, 1]], 0)], []), "an empty channel name is refused"
assert rejects(
    [deck("a", [[0, 0], [1, 1]], 0), deck("a", [[0, 0], [2, 2]], 0)], []
), "a repeated channel name is refused"
assert rejects([deck("a", [[0, 0]], 0)], []), "a one-rung ladder is refused"
assert rejects([deck("a", [[0, 0], [1, 1, 1]], 0)], []), "a three-entry rung is refused"
assert rejects([deck("a", [[0, 0], [1, "x"]], 0)], []), "a non-numeric rung entry is refused"
assert rejects([deck("a", [[5, 0], [5, 1]], 0)], []), "repeated tick figures are refused"
assert rejects([deck("a", [[0, 0], [1, 1]], 1.5)], []), "a fractional bias is refused"
assert rejects([deck("a", [[0, 0], [1, 1]], 0)], "no"), "samples must be a list"
assert rejects([deck("a", [[0, 0], [1, 1]], 0)], [{"channel": "a"}]), "a missing sample key is refused"
assert rejects([deck("a", [[0, 0], [1, 1]], 0)], [took("b", 0)]), "an undeclared channel is refused"
assert rejects([deck("a", [[0, 0], [1, 1]], 0)], [took("a", 0.5)]), "a fractional count is refused"
assert rejects(
    [deck("a", [[0, 0], [1, 1]], 0)], [took("a", 5000000)]
), "a count beyond a million is refused"
print("ok")
