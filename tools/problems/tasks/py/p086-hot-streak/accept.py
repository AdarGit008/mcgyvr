from solution import hot_streak

assert hot_streak([1, 5, 6, 2, 7, 8, 9], 4) == [4, 3], "later longer streak wins"
assert hot_streak([5, 6, 1, 7, 8], 4) == [0, 2], "a length tie goes to the earlier streak"
assert hot_streak([9, 9], 1) == [0, 2], "the whole list can be one streak"
assert hot_streak([1, 2], 5) == [-1, 0], "no game clears the bar"
assert hot_streak([4, 4], 4) == [-1, 0], "matching the bar exactly does not clear it"
assert hot_streak([1, 9, 9, 9], 5) == [1, 3], "a streak may run to the end"
assert hot_streak([10], 2) == [0, 1], "a single clearing game is a streak of one"
assert hot_streak([], 0) == [-1, 0], "no games at all"
assert hot_streak([-2, -1, -8], -5) == [0, 2], "a negative bar works the same way"
print("ok")
