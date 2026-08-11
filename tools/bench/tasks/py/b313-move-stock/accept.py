from solution import move_stock

assert move_stock(10, [5, -3]) == 12, "in then out"
assert move_stock(10, [-20]) == 0, "a removal cannot go below zero"
assert move_stock(0, []) == 0, "nothing happens"
assert move_stock(5, [-2, -2, -2]) == 0, "the floor holds part way"
assert move_stock(0, [3]) == 3, "a delivery into an empty store"
assert move_stock(2, [-5, 4]) == 4, "the floor resets what follows"
print("ok")
