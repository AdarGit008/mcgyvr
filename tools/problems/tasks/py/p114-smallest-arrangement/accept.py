from solution import smallest_arrangement

assert smallest_arrangement([1]) == "a", "single letter"
assert smallest_arrangement([2]) == "aa", "a double run is allowed"
assert smallest_arrangement([2, 1]) == "aab", "simple greedy case"
assert smallest_arrangement([3, 1]) == "aaba", "run must break at two"
assert smallest_arrangement([4, 1]) == "aabaa", "separator splits two doubles"
assert smallest_arrangement([2, 2]) == "aabb", "double double"
assert smallest_arrangement([1, 1, 1]) == "abc", "three distinct letters"
assert smallest_arrangement([0, 2]) == "bb", "leading zero count skips a"
assert smallest_arrangement([2, 4]) == "abbabb", "lookahead beats naive greed"
assert smallest_arrangement([0, 1, 0, 3]) == "dbdd", "the lone b is a separator"


def rejects(counts):
    try:
        smallest_arrangement(counts)
    except ValueError:
        return True
    return False


assert rejects([3]), "three of one letter alone"
assert rejects([5, 1]), "too few separators"
assert rejects([]), "empty list"
assert rejects([1, 1, 1, 1, 1]), "too many counts"
assert rejects([0, 0]), "all zero"
assert rejects([13]), "count above cap"
assert rejects([-1, 2]), "negative count"
assert rejects([True, 1]), "boolean count"
print("ok")
