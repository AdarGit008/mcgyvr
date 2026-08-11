from solution import quarter_hour


def rejects(minutes):
    try:
        quarter_hour(minutes)
    except Exception:
        return True
    return False


assert quarter_hour(20) == 15, "brought down to the quarter"
assert quarter_hour(15) == 15, "already on a quarter"
assert quarter_hour(14) == 0, "just short of the first quarter"
assert quarter_hour(0) == 0, "no minutes at all"
assert quarter_hour(59) == 45, "the last quarter of the hour"
assert rejects(-1), "negative minutes are rejected"
print("ok")
