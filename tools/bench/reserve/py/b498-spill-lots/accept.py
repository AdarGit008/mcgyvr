from solution import spill_lots

assert spill_lots([["a", "b"], ["c"]]) == ["a", "b", "c"], "lots tip out in order"
assert spill_lots([["a", ""], ["b"]]) == ["a", "b"], "an entry holding nothing is left behind"
assert spill_lots([[], ["c"]]) == ["c"], "a lot holding nothing adds nothing"
assert spill_lots([["a"], ["a"]]) == ["a", "a"], "the same entry in two lots"
assert spill_lots([[]]) == [], "one lot holding nothing"
assert spill_lots([]) == [], "no lots at all"
print("ok")
