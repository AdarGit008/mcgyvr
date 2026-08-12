from solution import apply_bps, split_evenly, sum_parts

assert split_evenly(100, 4) == [25, 25, 25, 25], "an even total splits evenly"
assert split_evenly(10, 3) == [4, 3, 3], "the extra cent lands on the first part"
assert split_evenly(101, 2) == [51, 50], "an odd cent goes to the earlier part"
assert split_evenly(2, 3) == [1, 1, 0], "more parts than cents pads with zeros"
assert split_evenly(0, 3) == [0, 0, 0], "a zero total is all zeros"
assert split_evenly(7, 1) == [7], "one part takes the whole total"
assert sum_parts(split_evenly(999, 7)) == 999, "the parts always re-total"
assert apply_bps(10000, 250) == 250, "a round basis-point cut is exact"
assert apply_bps(3333, 150) == 50, "a half-cent rounds up"


def rejects(*args):
    try:
        split_evenly(*args)
    except Exception:
        return True
    return False


assert rejects(10.5, 2), "fractional total is rejected"
assert rejects(-1, 2), "negative total is rejected"
assert rejects(10, 0), "zero ways is rejected"
print("ok")
