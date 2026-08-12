from solution import ridge_row

assert ridge_row([3, 1, 2], 1) == "###", "the ground row is solid across the transect"
assert ridge_row([3, 1, 2], 2) == "#.#", "a middle row shows only the taller stations"
assert ridge_row([3, 1, 2], 3) == "#..", "the top row keeps only the summit"
assert ridge_row([3, 1, 2], 4) == "...", "a level above the ridge is all dots"
assert ridge_row([0, 2], 1) == ".#", "a zero-elevation station never marks"
assert ridge_row([], 1) == "", "no stations gives the empty row"
assert ridge_row([5], 5) == "#", "an elevation exactly at the level marks"


def rejects(*args):
    try:
        ridge_row(*args)
    except Exception:
        return True
    return False


assert rejects(42, 1), "a non-list is rejected"
assert rejects([-1], 1), "a negative elevation is rejected"
assert rejects([1.5], 1), "a fractional elevation is rejected"
assert rejects([2], 0), "a zero level is rejected"
print("ok")
