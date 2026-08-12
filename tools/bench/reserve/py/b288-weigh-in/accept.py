from solution import weigh_in


def rejects(value):
    try:
        weigh_in(value)
    except Exception:
        return True
    return False


assert weigh_in(2500) == [2, 500], "two kilos and a half"
assert weigh_in(999) == [0, 999], "under a kilo"
assert weigh_in(1000) == [1, 0], "exactly a kilo"
assert weigh_in(0) == [0, 0], "nothing weighs nothing"
assert weigh_in(12345) == [12, 345], "a heavier load"
assert rejects(-1), "a negative weight is rejected"
print("ok")
