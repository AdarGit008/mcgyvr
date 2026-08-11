from solution import short_unit, label_of


def rejects(amount, unit):
    try:
        label_of(amount, unit)
    except Exception:
        return True
    return False


assert short_unit("metre") == "met", "the first three letters"
assert short_unit("kg") == "kg", "a short name is already short"
assert label_of(1, "metre") == "1 metre", "one takes the singular"
assert label_of(2, "metre") == "2 metres", "two takes the plural"
assert label_of(0, "metre") == "0 metres", "none takes the plural too"
assert rejects(-1, "metre"), "a negative amount is rejected"
print("ok")
