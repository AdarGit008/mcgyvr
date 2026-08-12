from solution import take_down


def rejects(held, amount):
    try:
        take_down(held, amount)
    except Exception:
        return True
    return False


assert take_down(10, 3) == 7, "three taken from ten"
assert take_down(10, 10) == 0, "everything taken"
assert take_down(10, 0) == 10, "nothing taken"
assert take_down(0, 0) == 0, "nothing held and nothing taken"
assert take_down(5, 1) == 4, "one taken from five"
assert rejects(5, 6), "taking too much is rejected"
print("ok")
