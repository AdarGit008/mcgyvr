from solution import settle_swap_requests


def duty(day, post, worker):
    return {"day": day, "post": post, "worker": worker}


def swap(left, right):
    return {"left": left, "right": right}


def depot(**changes):
    board = {
        "duties": [
            duty(1, "gate", "ana"),
            duty(2, "dock", "bo"),
            duty(3, "gate", "cy"),
            duty(4, "dock", "ana"),
            duty(2, "gate", "dee"),
            duty(5, "dock", "bo"),
        ],
        "cleared": [
            {"worker": "ana", "posts": ["gate", "dock"]},
            {"worker": "bo", "posts": ["gate", "dock"]},
            {"worker": "cy", "posts": ["gate"]},
            {"worker": "dee", "posts": ["gate", "dock"]},
        ],
        "peak": [2, 4],
        "cap": 1,
        "quota": 1,
    }
    board.update(changes)
    return board


assert settle_swap_requests(
    depot(),
    [
        swap([1, "gate"], [3, "gate"]),
        swap([3, "gate"], [2, "dock"]),
        swap([2, "gate"], [2, "dock"]),
        swap([1, "gate"], [2, "gate"]),
        swap([9, "gate"], [1, "gate"]),
        swap([4, "dock"], [4, "dock"]),
        swap([3, "gate"], [4, "dock"]),
        swap([1, "gate"], [2, "dock"]),
        swap([5, "dock"], [2, "dock"]),
    ],
) == {
    "rulings": [
        "taken",
        "peak",
        "taken",
        "quota",
        "unknown",
        "same",
        "same",
        "uncleared",
        "clash",
    ],
    "roster": [
        "1 gate cy",
        "2 dock dee",
        "2 gate bo",
        "3 gate ana",
        "4 dock ana",
        "5 dock bo",
    ],
}, "every refusal reason and two grants over one board"

assert settle_swap_requests(depot(), []) == {
    "rulings": [],
    "roster": [
        "1 gate ana",
        "2 dock bo",
        "2 gate dee",
        "3 gate cy",
        "4 dock ana",
        "5 dock bo",
    ],
}, "no requests leaves the board as it opened"

assert settle_swap_requests(depot(quota=0), [swap([1, "gate"], [3, "gate"])]) == {
    "rulings": ["quota"],
    "roster": [
        "1 gate ana",
        "2 dock bo",
        "2 gate dee",
        "3 gate cy",
        "4 dock ana",
        "5 dock bo",
    ],
}, "a quota of nought grants nothing"

assert settle_swap_requests(
    depot(peak=[], cap=0, quota=5), [swap([2, "dock"], [4, "dock"])]
) == {
    "rulings": ["taken"],
    "roster": [
        "1 gate ana",
        "2 dock ana",
        "2 gate dee",
        "3 gate cy",
        "4 dock bo",
        "5 dock bo",
    ],
}, "with no peak days the cap never bites"

assert settle_swap_requests(
    {
        "duties": [duty(1, "a", "pat"), duty(1, "b", "quin")],
        "cleared": [
            {"worker": "pat", "posts": ["a", "b"]},
            {"worker": "quin", "posts": ["a", "b"]},
        ],
        "peak": [],
        "cap": 0,
        "quota": 4,
    },
    [swap([1, "a"], [1, "b"]), swap([1, "a"], [1, "b"])],
) == {
    "rulings": ["taken", "taken"],
    "roster": ["1 a pat", "1 b quin"],
}, "two grants in a row put the board back where it began"


def rejects(*args):
    try:
        settle_swap_requests(*args)
    except ValueError:
        return True
    return False


assert rejects("no", []), "the board must be a record"
assert rejects({"duties": [], "cleared": [], "peak": [], "cap": 0}, []), "a missing board key is refused"
assert rejects(depot(duties=[duty(0, "a", "pat")]), []), "a day of nought is refused"
assert rejects(
    depot(duties=[duty(1, "a", "pat"), duty(1, "a", "quin")]), []
), "two duties on one day and post are refused"
assert rejects(
    {
        "duties": [duty(1, "a", "pat"), duty(1, "b", "pat")],
        "cleared": [{"worker": "pat", "posts": ["a", "b"]}],
        "peak": [],
        "cap": 0,
        "quota": 1,
    },
    [],
), "a worker opening on two posts of one day is refused"
assert rejects(
    depot(cleared=[{"worker": "ana", "posts": ["gate"]}]), []
), "a worker with no clearance is refused"
assert rejects(depot(peak=[2, 2]), []), "a repeated peak day is refused"
assert rejects(depot(cap=-1), []), "a negative cap is refused"
assert rejects(depot(), "no"), "requests must be a list"
assert rejects(depot(), [{"left": [1, "gate"]}]), "a request missing a side is refused"
assert rejects(depot(), [swap([1, "gate"], [2])]), "a one-entry side is refused"
assert rejects(depot(), [swap([1, "gate"], [2, ""])]), "an empty post on a side is refused"
print("ok")
