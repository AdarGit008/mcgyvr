from solution import bracket_seed_order

assert bracket_seed_order(2) == [1, 2], "two entrants meet at once"
assert bracket_seed_order(4) == [1, 4, 2, 3], "four entrants split the halves"
assert bracket_seed_order(8) == [
    1,
    8,
    4,
    5,
    2,
    7,
    3,
    6,
], "eight entrants, seed 2 anchors the bottom half"
assert bracket_seed_order(16) == [
    1,
    16,
    8,
    9,
    4,
    13,
    5,
    12,
    2,
    15,
    7,
    10,
    3,
    14,
    6,
    11,
], "sixteen entrants in canonical order"
sheet = bracket_seed_order(8)
assert sheet.index(2) >= 4, "seeds 1 and 2 sit in opposite halves"
assert sheet.index(3) >= 4 and sheet.index(4) < 4, "seeds 3 and 4 land opposite 2 and 1"


def rejects(count):
    try:
        bracket_seed_order(count)
    except ValueError:
        return True
    return False


assert rejects(3), "non-power count rejected"
assert rejects(0), "zero rejected"
assert rejects(1), "a lone entrant rejected"
assert rejects(2.5), "fractional count rejected"
print("ok")
