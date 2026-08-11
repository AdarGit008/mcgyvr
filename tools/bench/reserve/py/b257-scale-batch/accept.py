from solution import scale_batch


def rejects(amounts, factor):
    try:
        scale_batch(amounts, factor)
    except Exception:
        return True
    return False


assert scale_batch([2, 3], 2) == [4, 6], "doubling stays whole"
assert scale_batch([1, 2], 1.5) == [2, 3], "a half rounds up"
assert scale_batch([4], 0) == [0], "scaling to nothing"
assert scale_batch([], 2) == [], "no ingredients"
assert scale_batch([3], 1) == [3], "an unchanged batch"
assert rejects([1], -1), "a negative factor is rejected"
print("ok")
