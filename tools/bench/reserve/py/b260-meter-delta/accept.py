from solution import meter_delta


def rejects(before, after, ceiling):
    try:
        meter_delta(before, after, ceiling)
    except Exception:
        return True
    return False


assert meter_delta(10, 25, 100) == 15, "a plain climb"
assert meter_delta(90, 10, 100) == 20, "the meter wrapped"
assert meter_delta(5, 5, 100) == 0, "the meter did not move"
assert meter_delta(0, 99, 100) == 99, "the whole span but the ceiling"
assert rejects(100, 5, 100), "the earlier reading is too big"
assert rejects(5, 150, 100), "the later reading is too big"
print("ok")
