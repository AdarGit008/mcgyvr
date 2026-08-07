from solution import replay_agenda_boxes


def item(title, planned, actual, rule):
    return {"title": title, "planned": planned, "actual": actual, "rule": rule}


assert replay_agenda_boxes(
    [item("open", 10, 10, "absorb"), item("budget", 20, 15, "absorb")], 0
) == {
    "finish": 25,
    "spare": 5,
    "unfunded": 0,
    "log": ["open 0 10 exact", "budget 10 25 under"],
    "carry": [],
}, "an exact item and an underrun that refills the pool"

assert replay_agenda_boxes(
    [item("intro", 5, 12, "absorb"), item("demo", 30, 30, "absorb")], 10
) == {
    "finish": 42,
    "spare": 3,
    "unfunded": 0,
    "log": ["intro 0 12 over", "demo 12 42 exact"],
    "carry": [],
}, "the pool alone pays for a small overrun"

assert replay_agenda_boxes(
    [
        item("kickoff", 5, 20, "absorb"),
        item("review", 8, 8, "absorb"),
        item("close", 6, 2, "absorb"),
    ],
    2,
) == {
    "finish": 30,
    "spare": 0,
    "unfunded": 9,
    "log": ["kickoff 0 20 over", "review 20 28 over", "close 28 30 over"],
    "carry": [],
}, "trimming later boxes to one minute leaves the rest unfunded"

assert replay_agenda_boxes(
    [item("talk", 10, 25, "defer"), item("vote", 5, 3, "defer")], 0
) == {
    "finish": 13,
    "spare": 2,
    "unfunded": 0,
    "log": ["talk 0 10 cut", "vote 10 13 under"],
    "carry": ["talk 15"],
}, "a deferred item halts on its box and writes off the rest"

assert replay_agenda_boxes(
    [
        item("a", 4, 9, "defer"),
        item("b", 10, 14, "absorb"),
        item("c", 9, 9, "absorb"),
    ],
    1,
) == {
    "finish": 27,
    "spare": 0,
    "unfunded": 3,
    "log": ["a 0 4 cut", "b 4 18 over", "c 18 27 over"],
    "carry": ["a 5"],
}, "a trimmed box turns a matching item into an overrun of its own"

assert replay_agenda_boxes([], 7) == {
    "finish": 0,
    "spare": 7,
    "unfunded": 0,
    "log": [],
    "carry": [],
}, "no items leaves the pool untouched"

assert replay_agenda_boxes([item("skip", 7, 0, "absorb")], 0) == {
    "finish": 0,
    "spare": 7,
    "unfunded": 0,
    "log": ["skip 0 0 under"],
    "carry": [],
}, "an item taking no minutes at all still hands its box back"


def rejects(*args):
    try:
        replay_agenda_boxes(*args)
    except ValueError:
        return True
    return False


assert rejects("nope", 0), "items must be a list"
assert rejects([5], 0), "an item must be a record"
assert rejects([{"title": "x", "planned": 3, "actual": 3}], 0), "a missing key is refused"
assert rejects([item("", 3, 3, "absorb")], 0), "an empty title is refused"
assert rejects(
    [item("x", 3, 3, "absorb"), item("x", 4, 4, "defer")], 0
), "a shared title is refused"
assert rejects([item("x", 0, 3, "absorb")], 0), "a planned box of nought is refused"
assert rejects([item("x", 3, -1, "absorb")], 0), "a negative actual is refused"
assert rejects([item("x", 3, 3, "shift")], 0), "an unknown rule is refused"
assert rejects([item("x", 3, 3, "absorb")], -2), "a negative slack is refused"
print("ok")
