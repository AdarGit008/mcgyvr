from solution import run_till_session

PRICES = {"tea": 250, "bun": 180, "jam": 320}

assert run_till_session([], PRICES) == {
    "state": "open",
    "items": [],
    "total": 0,
    "paid": 0,
    "change": 0,
}, "empty session stays open"
assert run_till_session([["scan", "tea"], ["scan", "bun"], ["scan", "tea"]], PRICES) == {
    "state": "open",
    "items": [["bun", 1], ["tea", 2]],
    "total": 0,
    "paid": 0,
    "change": 0,
}, "scans accumulate and items sort by name"
assert run_till_session([["scan", "tea"], ["scan", "bun"], ["void", "tea"]], PRICES) == {
    "state": "open",
    "items": [["bun", 1]],
    "total": 0,
    "paid": 0,
    "change": 0,
}, "a void at one unit drops the item"
assert run_till_session([["scan", "tea"], ["scan", "tea"], ["void", "tea"]], PRICES) == {
    "state": "open",
    "items": [["tea", 1]],
    "total": 0,
    "paid": 0,
    "change": 0,
}, "a void above one unit decrements"
assert run_till_session([["scan", "tea"], ["scan", "bun"], ["close"]], PRICES) == {
    "state": "payment",
    "items": [["bun", 1], ["tea", 1]],
    "total": 430,
    "paid": 0,
    "change": 0,
}, "close fixes the total"
assert run_till_session(
    [["scan", "tea"], ["scan", "bun"], ["close"], ["pay", 200]], PRICES
) == {
    "state": "payment",
    "items": [["bun", 1], ["tea", 1]],
    "total": 430,
    "paid": 200,
    "change": 0,
}, "a partial payment keeps the session in payment"
assert run_till_session([["scan", "bun"], ["close"], ["pay", 180]], PRICES) == {
    "state": "paid",
    "items": [["bun", 1]],
    "total": 180,
    "paid": 180,
    "change": 0,
}, "an exact payment closes with no change"
assert run_till_session([["scan", "tea"], ["close"], ["pay", 300]], PRICES) == {
    "state": "paid",
    "items": [["tea", 1]],
    "total": 250,
    "paid": 300,
    "change": 50,
}, "an overpayment returns change"
assert run_till_session([["scan", "jam"], ["close"], ["pay", 100], ["pay", 300]], PRICES) == {
    "state": "paid",
    "items": [["jam", 1]],
    "total": 320,
    "paid": 400,
    "change": 80,
}, "payments accumulate across events"
assert run_till_session([["scan", "tea"], ["cancel"]], PRICES) == {
    "state": "cancelled",
    "items": [["tea", 1]],
    "total": 0,
    "paid": 0,
    "change": 0,
}, "cancel from open keeps the cart"
assert run_till_session([["scan", "tea"], ["close"], ["pay", 100], ["cancel"]], PRICES) == {
    "state": "cancelled",
    "items": [["tea", 1]],
    "total": 250,
    "paid": 100,
    "change": 0,
}, "cancel during payment keeps the cents received"


def rejects(*args):
    try:
        run_till_session(*args)
    except ValueError:
        return True
    return False


assert rejects([], {"tea": 0}), "price of zero"
assert rejects([["grab", "tea"]], PRICES), "unknown action"
assert rejects([["scan"]], PRICES), "scan without an item"
assert rejects([["scan", "ale"]], PRICES), "scan of an unpriced item"
assert rejects([["void", "tea"]], PRICES), "void of an item not in the cart"
assert rejects([["pay", 100]], PRICES), "pay while open"
assert rejects([["scan", "tea"], ["close"], ["scan", "bun"]], PRICES), "scan during payment"
assert rejects([["scan", "tea"], ["close"], ["pay", 0]], PRICES), "pay amount of zero"
assert rejects([["scan", "tea"], ["close"], ["pay", 99.5]], PRICES), "fractional pay amount"
assert rejects(
    [["scan", "bun"], ["close"], ["pay", 180], ["scan", "tea"]], PRICES
), "event after the session is paid"
assert rejects([["cancel"], ["scan", "tea"]], PRICES), "event after the session is cancelled"
assert rejects([["close"]], PRICES), "close with an empty cart"
print("ok")
