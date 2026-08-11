from solution import ring_slot

assert ring_slot(8, 3, 0) == 0, "before wrapping the oldest sits in slot 0"
assert ring_slot(8, 3, 2) == 2, "before wrapping rank k sits in slot k"
assert ring_slot(4, 4, 3) == 3, "an exactly full recorder has not wrapped"
assert ring_slot(4, 6, 0) == 2, "after wrapping the oldest survivor moved up"
assert ring_slot(4, 6, 3) == 1, "the newest survivor sits before the oldest slot"
assert ring_slot(3, 10, 1) == 2, "a long run keeps wrapping around"


def rejects(*args):
    try:
        ring_slot(*args)
    except ValueError:
        return True
    return False


assert rejects(0, 3, 0), "a zero capacity is rejected"
assert rejects(4, -1, 0), "negative writes are rejected"
assert rejects(4, 4, 1.5), "a fractional rank is rejected"
assert rejects(4, 6, 4), "a rank past the survivors is rejected"
assert rejects(5, 0, 0), "an empty recorder has no survivors"
print("ok")
