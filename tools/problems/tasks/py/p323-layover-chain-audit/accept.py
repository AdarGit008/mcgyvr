from solution import check_layovers

pair = [
    {"ref": "h1", "board": "K", "alight": "L", "leaves": 60, "lands": 90},
    {"ref": "h2", "board": "L", "alight": "M", "leaves": 105, "lands": 140},
]

assert check_layovers(pair, 15, 0) == {
    "verdict": "sound",
    "at": -1,
    "arrive": 140,
}, "a wait of exactly the layover is enough"
assert check_layovers(pair, 16, 0) == {
    "verdict": "tight",
    "at": 1,
    "arrive": -1,
}, "one minute more than the wait allows faults the second hop"
assert check_layovers(pair, 15, 60) == {
    "verdict": "sound",
    "at": -1,
    "arrive": 140,
}, "leaving exactly at ready_at is not early"
assert check_layovers(pair, 15, 61) == {
    "verdict": "early",
    "at": 0,
    "arrive": -1,
}, "the opening hop leaves before the traveller is ready"

wrong_halt = [
    {"ref": "h1", "board": "K", "alight": "L", "leaves": 60, "lands": 90},
    {"ref": "h2", "board": "N", "alight": "M", "leaves": 95, "lands": 140},
]
assert check_layovers(wrong_halt, 15, 0) == {
    "verdict": "place",
    "at": 1,
    "arrive": -1,
}, "a hop faulted both ways is faulted as place"
assert check_layovers(wrong_halt, 0, 0) == {
    "verdict": "place",
    "at": 1,
    "arrive": -1,
}, "the halt still fails when no wait is demanded"

single = [{"ref": "h1", "board": "K", "alight": "L", "leaves": 60, "lands": 90}]
assert check_layovers(single, 99, 0) == {
    "verdict": "sound",
    "at": -1,
    "arrive": 90,
}, "a lone hop has no change to audit"
assert check_layovers(single, 99, 61) == {
    "verdict": "early",
    "at": 0,
    "arrive": -1,
}, "a lone hop can still be early"

triple = [
    {"ref": "h1", "board": "K", "alight": "L", "leaves": 60, "lands": 90},
    {"ref": "h2", "board": "L", "alight": "M", "leaves": 105, "lands": 140},
    {"ref": "h3", "board": "M", "alight": "P", "leaves": 150, "lands": 175},
]
assert check_layovers(triple, 10, 0) == {
    "verdict": "sound",
    "at": -1,
    "arrive": 175,
}, "three hops with exact waits throughout"
assert check_layovers(triple, 11, 0) == {
    "verdict": "tight",
    "at": 2,
    "arrive": -1,
}, "the third hop is the first to fault"


def rejects(*args):
    try:
        check_layovers(*args)
    except ValueError:
        return True
    return False


assert rejects([], 5, 0), "an empty chain is rejected"
assert rejects("chain", 5, 0), "a non-list chain is rejected"
assert rejects(
    [{"ref": "h1", "board": "K", "alight": "L", "leaves": 60}], 5, 0
), "a hop missing lands is rejected"
assert rejects(
    [{"ref": "h1", "board": "K", "alight": "K", "leaves": 60, "lands": 90}], 5, 0
), "boarding and alighting at one halt is rejected"
assert rejects(
    [{"ref": "h1", "board": "K", "alight": "L", "leaves": 90, "lands": 90}], 5, 0
), "landing no later than leaving is rejected"
assert rejects(
    [{"ref": "", "board": "K", "alight": "L", "leaves": 60, "lands": 90}], 5, 0
), "an empty ref is rejected"
assert rejects(pair, -1, 0), "a negative layover is rejected"
assert rejects(pair, 5, "soon"), "a non-numeric ready_at is rejected"
print("ok")
