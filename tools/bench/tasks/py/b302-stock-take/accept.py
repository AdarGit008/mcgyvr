from solution import unit_price


def rejects(total, count):
    try:
        unit_price(total, count)
    except Exception:
        return True
    return False


assert unit_price(1000, 4) == 250, "an exact division"
assert unit_price(999, 4) == 249, "rounded down"
assert unit_price(100, 3) == 33, "a third, rounded down"
assert unit_price(0, 5) == 0, "nothing costs nothing each"
assert unit_price(7, 7) == 1, "one each"
assert rejects(100, 0), "a count of zero is rejected"
print("ok")
