from solution import toggle_range

assert toggle_range(0, 0, 3) == 15, "positions 0..3 of zero become 1111"
assert toggle_range(10, 1, 2) == 12, "middle bits invert"
assert toggle_range(5, 0, 0) == 4, "single-bit range flips exactly one bit"
assert toggle_range(0, 29, 29) == 536870912, "topmost allowed bit flips"
assert toggle_range(1023, 0, 9) == 0, "full range of set bits clears them"
assert toggle_range(0, 0, 29) == 1073741823, "whole 30-bit span inverts"
assert toggle_range(toggle_range(777, 3, 17), 3, 17) == 777, (
    "toggling twice restores the value"
)


def rejects(*args):
    try:
        toggle_range(*args)
    except ValueError:
        return True
    return False


assert rejects(1, 3, 2), "lo above hi is rejected"
assert rejects(1, 0, 30), "position 30 is rejected"
assert rejects(1, -1, 3), "negative position is rejected"
assert rejects(-1, 0, 3), "negative value is rejected"
assert rejects(2**30, 0, 3), "value at 2**30 is rejected"
assert rejects(1.5, 0, 3), "fractional value is rejected"
print("ok")
