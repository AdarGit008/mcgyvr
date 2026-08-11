from solution import shelf_fit

assert shelf_fit([], 50) == 0, "no books shelves nothing"
assert shelf_fit([20], 50) == 1, "a single book fits"
assert shelf_fit([60], 50) == 0, "a first book too wide shelves nothing"
assert shelf_fit([20, 30], 50) == 2, "an exact fill is allowed"
assert shelf_fit([20, 31, 5], 50) == 1, "shelving stops at the first misfit even when a later book would fit"
assert shelf_fit([10, 10, 10, 10], 35) == 3, "shelving stops when the shelf runs out"
assert shelf_fit([5, 5], 0) == 0, "a zero-width shelf holds nothing"


def rejects(*args):
    try:
        shelf_fit(*args)
    except ValueError:
        return True
    return False


assert rejects(42, 50), "a non-list is rejected"
assert rejects([20, 0], 50), "a zero spine width anywhere is rejected"
assert rejects([2.5], 50), "a fractional spine width is rejected"
assert rejects([20], -1), "a negative shelf width is rejected"
print("ok")
