from solution import shuffle_deal, deal_counts

assert shuffle_deal(["a", "b", "c", "d"], 2) == [
    ["a", "c"],
    ["b", "d"],
], "cards alternate round the table"
assert shuffle_deal(["a"], 2) == [["a"], []], "one card, one hand short"
assert shuffle_deal([], 2) == [[], []], "empty hands are still dealt"
assert shuffle_deal(["a", "b"], 0) == [], "no hands, nothing dealt"
assert deal_counts([["a", "c"], ["b"]]) == [2, 1], "the sizes of each hand"
assert deal_counts([]) == [], "no hands to count"
print("ok")
