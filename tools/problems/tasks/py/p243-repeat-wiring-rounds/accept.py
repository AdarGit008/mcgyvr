from solution import apply_cycle_power

assert apply_cycle_power([1, 0, 3, 4, 2], 0) == [
    0,
    1,
    2,
    3,
    4,
], "zero rounds leaves every plug alone"
assert apply_cycle_power([1, 0, 3, 4, 2], 1) == [
    1,
    0,
    3,
    4,
    2,
], "one round is the panel itself"
assert apply_cycle_power([1, 0, 3, 4, 2], 2) == [
    0,
    1,
    4,
    2,
    3,
], "two rounds settles the pair and turns the triple"
assert apply_cycle_power([1, 0, 3, 4, 2], 5) == [
    1,
    0,
    4,
    2,
    3,
], "five rounds slides each ring by its own remainder"
assert apply_cycle_power([1, 0, 3, 4, 2], 6) == [
    0,
    1,
    2,
    3,
    4,
], "six rounds is a whole number of turns for both rings"
assert apply_cycle_power([1, 2, 3, 0, 5, 4], 6) == [
    2,
    3,
    0,
    1,
    4,
    5,
], "a four-ring and a two-ring reduce differently"
assert apply_cycle_power([0, 1, 2], 100) == [
    0,
    1,
    2,
], "a panel that moves nothing stays put"
assert apply_cycle_power([0], 9) == [0], "a one-slot panel"


def rejects(panel, rounds):
    try:
        apply_cycle_power(panel, rounds)
    except ValueError:
        return True
    return False


assert rejects("panel", 1), "a non-list panel is rejected"
assert rejects([], 1), "an empty panel is rejected"
assert rejects([0.5], 1), "a fractional entry is rejected"
assert rejects([None, 0], 1), "a non-number entry is rejected"
assert rejects([2, 0], 1), "a slot the panel lacks is rejected"
assert rejects([1, 1], 1), "a slot named twice is rejected"
assert rejects([0, 1], -1), "a negative round count is rejected"
assert rejects([0, 1], 1.5), "a fractional round count is rejected"
assert rejects([0, 1], "3"), "a non-number round count is rejected"
print("ok")
