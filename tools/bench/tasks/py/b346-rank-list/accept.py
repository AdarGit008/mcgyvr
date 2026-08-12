from solution import rank_of, rank_all

assert rank_of(5, [5, 3]) == 1, "nothing stands above it"
assert rank_of(3, [5, 3]) == 2, "one score stands above it"
assert rank_all([5, 5, 3]) == [1, 1, 3], "the tie shares a rank"
assert rank_all([3, 5]) == [2, 1], "in the order given"
assert rank_all([]) == [], "no scores at all"
assert rank_all([7]) == [1], "one score leads"
assert rank_all([4, 4, 4]) == [1, 1, 1], "everyone ties"
print("ok")
