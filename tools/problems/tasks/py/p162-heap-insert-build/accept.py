from solution import build_min_heap_by_insertion

assert build_min_heap_by_insertion([]) == [], "empty supply"
assert build_min_heap_by_insertion([7]) == [7], "single value"
assert build_min_heap_by_insertion([5, 3, 8, 1]) == [1, 3, 8, 5], "two lifts"
assert build_min_heap_by_insertion([9, 7, 5, 3, 1]) == [1, 3, 7, 9, 5], "descending"
assert build_min_heap_by_insertion([1, 2, 3]) == [1, 2, 3], "no trade needed"
assert build_min_heap_by_insertion([4, 4, 4]) == [4, 4, 4], "equal never trades"
assert build_min_heap_by_insertion([-2, -9]) == [-9, -2], "negatives"
assert build_min_heap_by_insertion([6, 2, 9, 0, 4, 8]) == [0, 2, 8, 6, 4, 9], "six"
assert build_min_heap_by_insertion([0, 0, 1, 0]) == [0, 0, 1, 0], "zeros hold"


def rejects(value):
    try:
        build_min_heap_by_insertion(value)
    except ValueError:
        return True
    return False


assert rejects("abc"), "string is not a list"
assert rejects(None), "none is not a list"
assert rejects([1, 2.5]), "fraction rejected"
assert rejects([1, "3"]), "text entry rejected"
assert rejects([1, True]), "boolean rejected"
assert rejects(17), "bare number is not a list"
print("ok")
