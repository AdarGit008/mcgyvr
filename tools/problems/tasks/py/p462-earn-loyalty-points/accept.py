from solution import earn_loyalty_points

LADDER = [
    {"from": 0, "per": 1},
    {"from": 50000, "per": 2},
    {"from": 200000, "per": 3},
]

assert earn_loyalty_points([10000, 45000, 100000, 60000], LADDER) == [
    10,
    45,
    200,
    120,
], "each receipt earns at the rung its opening outlay falls in"
assert earn_loyalty_points([50000], LADDER) == [
    50
], "the outlay grows only after the receipt has earned"
assert earn_loyalty_points([49999, 1, 1000], LADDER) == [
    49,
    0,
    2,
], "the rung lifts once the running outlay reaches it"
assert earn_loyalty_points([1999, 999], [{"from": 0, "per": 3}]) == [
    5,
    2,
], "a part of a thousand cents is thrown away"
assert earn_loyalty_points([1000, 0, 7000], [{"from": 0, "per": 0}]) == [
    0,
    0,
    0,
], "a rung paying nothing awards nothing"
assert earn_loyalty_points([], LADDER) == [], "no receipts, no awards"
assert earn_loyalty_points([200000, 10], LADDER) == [
    200,
    0,
], "a receipt never straddles two rungs"


def rejects(receipts, ladder):
    try:
        earn_loyalty_points(receipts, ladder)
    except ValueError:
        return True
    return False


assert rejects([100], []), "empty ladder"
assert rejects([100], [{"from": 5, "per": 1}]), "the opening rung must sit at nought"
assert rejects(
    [100], [{"from": 0, "per": 1}, {"from": 0, "per": 2}]
), "from values must climb strictly"
assert rejects(
    [100], [{"from": 0, "per": 1, "bonus": 4}]
), "a rung carries exactly two keys"
assert rejects([100], [{"from": 0}]), "a rung missing per is rejected"
assert rejects([-1], LADDER), "a receipt below nought is rejected"
assert rejects([12.5], LADDER), "a receipt that is not whole is rejected"
assert rejects([100], [{"from": 0, "per": -2}]), "a per below nought is rejected"
assert rejects("nope", LADDER), "a non-list of receipts is rejected"
print("ok")
