from solution import bill_overage

assert bill_overage(10, 5, []) == {"billed": [], "carried": 0}, "no periods"
assert bill_overage(10, 5, [4]) == {
    "billed": [0],
    "carried": 5,
}, "unspent units carry up to the cap"
assert bill_overage(10, 5, [12]) == {
    "billed": [2],
    "carried": 0,
}, "consumption past the allowance is billed"
assert bill_overage(10, 5, [10]) == {
    "billed": [0],
    "carried": 0,
}, "an exactly spent period bills and carries nothing"
assert bill_overage(10, 5, [4, 9]) == {
    "billed": [0, 0],
    "carried": 5,
}, "carried units cover a later period"
assert bill_overage(10, 3, [0, 0]) == {
    "billed": [0, 0],
    "carried": 3,
}, "the cap holds the carry down"
assert bill_overage(10, 5, [15, 2]) == {
    "billed": [5, 0],
    "carried": 5,
}, "an overdrawn period carries nothing forward"
assert bill_overage(10, 0, [4, 11]) == {
    "billed": [0, 1],
    "carried": 0,
}, "a zero cap never carries"


def rejects(allowance, carry_cap, usage):
    try:
        bill_overage(allowance, carry_cap, usage)
    except Exception:
        return True
    return False


assert rejects(-1, 5, [1]), "negative allowance is rejected"
assert rejects(10, 2.5, [1]), "fractional carry cap is rejected"
assert rejects(10, 5, "heavy"), "non-list usage is rejected"
assert rejects(10, 5, [3, -1]), "negative usage entry is rejected"
print("ok")
