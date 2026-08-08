from solution import redeem_coupon_slips


def rejects(tickets, slips, ceiling):
    try:
        redeem_coupon_slips(tickets, slips, ceiling)
    except ValueError:
        return True
    return False


assert redeem_coupon_slips(
    [["gate", 1000], ["boat", 500]],
    [["s1", "gate", 10], ["s2", "gate", 10], ["s3", "raft", 50]],
    100000,
) == {
    "due": 1310,
    "saved": 190,
    "ignored": ["s3"],
}, "a second slip bites into what the first left behind"
assert redeem_coupon_slips(
    [["gate", 1000], ["boat", 500]],
    [["a", "gate", 10], ["b", "gate", 10], ["c", "gate", 10]],
    100000,
) == {"due": 1310, "saved": 190, "ignored": ["c"]}, "a third slip on one ticket is passed over"
assert redeem_coupon_slips([["gate", 1000]], [["a", "gate", 10], ["b", "gate", 10]], 195) == {
    "due": 810,
    "saved": 190,
    "ignored": [],
}, "a compounded saving fits under a ceiling the opening price would break"
assert redeem_coupon_slips([["gate", 1000]], [["a", "gate", 10], ["b", "gate", 10]], 150) == {
    "due": 900,
    "saved": 100,
    "ignored": ["b"],
}, "a slip past the ceiling is passed over whole"
assert redeem_coupon_slips(
    [["gate", 1000], ["boat", 500]],
    [["a", "gate", 50], ["b", "boat", 10], ["c", "gate", 5]],
    100,
) == {
    "due": 1400,
    "saved": 100,
    "ignored": ["a"],
}, "a slip stopped by the ceiling neither strikes nor stops those behind it"
assert redeem_coupon_slips(
    [["free", 0], ["gate", 1000]], [["a", "gate", 10], ["b", "free", 50]], 0
) == {
    "due": 1000,
    "saved": 0,
    "ignored": ["a"],
}, "a saving of nothing clears even a ceiling of nought"
assert redeem_coupon_slips([["gate", 1000]], [], 500) == {
    "due": 1000,
    "saved": 0,
    "ignored": [],
}, "no slips leaves the tickets whole"
assert redeem_coupon_slips([], [["a", "gate", 10]], 500) == {
    "due": 0,
    "saved": 0,
    "ignored": ["a"],
}, "a slip naming no ticket at all is passed over"
assert redeem_coupon_slips([["odd", 999]], [["a", "odd", 33]], 10000) == {
    "due": 670,
    "saved": 329,
    "ignored": [],
}, "a part of a cent is dropped"
assert redeem_coupon_slips([["gate", 800]], [["a", "gate", 100]], 10000) == {
    "due": 0,
    "saved": 800,
    "ignored": [],
}, "a share of the whole leaves nothing standing"

assert rejects([["gate"]], [], 100), "a ticket that is not a pair is refused"
assert rejects([["", 100]], [], 100), "an empty label is refused"
assert rejects([["gate", 100], ["gate", 200]], [], 100), "two tickets sharing a label are refused"
assert rejects([["gate", -1]], [], 100), "a negative price is refused"
assert rejects([["gate", 1.5]], [], 100), "a fractional price is refused"
assert rejects([["gate", 100]], [["a", "gate"]], 100), "a slip that is not a triple is refused"
assert rejects([["gate", 100]], [["", "gate", 10]], 100), "an empty tag is refused"
assert rejects(
    [["gate", 100]], [["a", "gate", 10], ["a", "gate", 20]], 100
), "two slips sharing a tag are refused"
assert rejects([["gate", 100]], [["a", "gate", 0]], 100), "a share of nought is refused"
assert rejects([["gate", 100]], [["a", "gate", 101]], 100), "a share past 100 is refused"
assert rejects([["gate", 100]], [["a", "gate", 1.5]], 100), "a fractional share is refused"
assert rejects([["gate", 100]], [], -1), "a negative ceiling is refused"
assert rejects([["gate", 100]], [], 2.5), "a fractional ceiling is refused"
print("ok")
