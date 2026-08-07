from solution import run_coin_drawer

kiosk = [[100, 2], [50, 1], [20, 3], [10, 1]]

assert run_coin_drawer(kiosk, []) == {
    "till": [[100, 2], [50, 1], [20, 3], [10, 1]],
    "turnedAway": [],
    "earnings": 0,
}, "an empty queue leaves the till alone"

assert run_coin_drawer(kiosk, [{"price": 30, "paid": [50]}]) == {
    "till": [[100, 2], [50, 2], [20, 2], [10, 1]],
    "turnedAway": [],
    "earnings": 30,
}, "one settled purchase"

assert run_coin_drawer(
    kiosk,
    [
        {"price": 30, "paid": [50]},
        {"price": 45, "paid": [100]},
        {"price": 100, "paid": [50, 50]},
        {"price": 60, "paid": [50]},
    ],
) == {
    "till": [[100, 2], [50, 4], [20, 2], [10, 1]],
    "turnedAway": [1, 3],
    "earnings": 130,
}, "two turned away and the till rolled back each time"

assert run_coin_drawer(
    [[25, 0], [10, 0], [5, 1]], [{"price": 20, "paid": [25, 10]}]
) == {
    "till": [[25, 1], [10, 0], [5, 0]],
    "turnedAway": [],
    "earnings": 20,
}, "the pushed coins are available as change"

assert run_coin_drawer([[6, 1], [4, 2]], [{"price": 2, "paid": [6, 4]}]) == {
    "till": [[6, 1], [4, 2]],
    "turnedAway": [0],
    "earnings": 0,
}, "the biggest-first walk may strand a balance a cleverer split would clear"

assert run_coin_drawer([[10, 1], [50, 2], [20, 0]], [{"price": 40, "paid": [50]}]) == {
    "till": [[50, 3], [20, 0], [10, 0]],
    "turnedAway": [],
    "earnings": 40,
}, "an unsorted till is reported biggest first"


def rejects(till, queue):
    try:
        run_coin_drawer(till, queue)
    except ValueError:
        return True
    return False


assert rejects(7, []), "a till that is not a list"
assert rejects([], []), "a till of no denominations"
assert rejects([[10]], []), "a till entry that is not a pair"
assert rejects([[0, 3]], []), "a denomination of nothing"
assert rejects([[10, -1]], []), "a negative count"
assert rejects([[10, 1], [10, 2]], []), "a denomination listed twice"
assert rejects(kiosk, 3), "a queue that is not a list"
assert rejects(kiosk, [5]), "a purchase that is not a record"
assert rejects(kiosk, [{"price": 0, "paid": [10]}]), "a price of nothing"
assert rejects(kiosk, [{"price": 1.5, "paid": [10]}]), "a fractional price"
assert rejects(kiosk, [{"price": 10, "paid": 10}]), "coins not a list"
assert rejects(kiosk, [{"price": 10, "paid": [3]}]), "a coin the till does not handle"
print("ok")
