from solution import slot_hits

assert slot_hits([], 4) == 0, "empty stream scores no hits"
assert slot_hits([7, 7, 7], 4) == 2, "repeats hit after the first miss"
assert slot_hits([1, 5, 1], 4) == 0, "colliding keys keep evicting each other"
assert slot_hits([0, 1, 2, 0, 1, 2], 4) == 3, "keys in distinct slots hit on return"
assert slot_hits([-3, -3], 4) == 1, "a negative key holds its slot"
assert slot_hits([-3, 1, -3], 4) == 0, "key -3 shares slot 1 with key 1"
assert slot_hits([4, 4], 1) == 1, "a single-slot cache still hits"


def rejects(keys, slots):
    try:
        slot_hits(keys, slots)
    except ValueError:
        return True
    return False


assert rejects([1], 0), "zero slots is rejected"
assert rejects([1], 2.5), "fractional slot count is rejected"
assert rejects([1.5], 4), "fractional key is rejected"
print("ok")
