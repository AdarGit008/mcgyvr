from solution import ledger_swing

assert ledger_swing([10, 14, 9]) == 5, "the widest of two moves"
assert ledger_swing([1, 10]) == 9, "a rise counts"
assert ledger_swing([10, 1]) == 9, "a fall counts the same"
assert ledger_swing([5]) == 0, "one balance cannot swing"
assert ledger_swing([]) == 0, "no balances, no swing"
assert ledger_swing([3, 3, 3]) == 0, "a flat ledger"
assert ledger_swing([0, -5, 2]) == 7, "across zero"
print("ok")
