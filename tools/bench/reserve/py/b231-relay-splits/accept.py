from solution import relay_splits


def rejects(value):
    try:
        relay_splits(value)
    except Exception:
        return True
    return False


assert relay_splits([12, 25, 40]) == [12, 13, 15], "three legs"
assert relay_splits([9]) == [9], "the first leg is the first reading"
assert relay_splits([]) == [], "no legs run"
assert relay_splits([1, 2, 3]) == [1, 1, 1], "even legs"
assert rejects([10, 10]), "a stalled clock is rejected"
assert rejects([10, 4]), "a clock going backwards is rejected"
print("ok")
