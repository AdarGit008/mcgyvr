from solution import best_harvest

assert best_harvest([]) == 0, "no days yields zero"
assert best_harvest([7]) == 7, "a single day is taken whole"
assert best_harvest([4, 9]) == 9, "adjacent days keep only the better"
assert best_harvest([5, 1, 1, 5]) == 10, "the ends beat any middle pick"
assert best_harvest([3, 2, 5, 10, 7]) == 15, "alternating picks add up"
assert best_harvest([1, 20, 3, 4, 25, 2]) == 45, "two heavy days with rest between"
assert best_harvest([0, 0, 0]) == 0, "all-zero days yield zero"


def rejects(value):
    try:
        best_harvest(value)
    except ValueError:
        return True
    return False


assert rejects(42), "non-list is rejected"
assert rejects([3, -1]), "negative yield is rejected"
assert rejects([1, 2.5]), "fractional yield is rejected"
print("ok")
