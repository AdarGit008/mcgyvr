from solution import fuel_legs


def rejects(litres, burn):
    try:
        fuel_legs(litres, burn)
    except Exception:
        return True
    return False


assert fuel_legs(10, 3) == 3, "the remainder buys no leg"
assert fuel_legs(9, 3) == 3, "an exact tank"
assert fuel_legs(2, 3) == 0, "not enough for one"
assert fuel_legs(0, 5) == 0, "an empty tank"
assert rejects(10, 0), "a burn of zero is rejected"
assert rejects(10, -2), "a negative burn is rejected"
print("ok")
