from solution import batch_ends

assert batch_ends(6, 2) == [1, 3, 5], "three full batches"
assert batch_ends(7, 2) == [1, 3, 5], "the part-batch is left out"
assert batch_ends(1, 2) == [], "not even one full batch"
assert batch_ends(0, 2) == [], "nothing to batch"
assert batch_ends(3, 3) == [2], "exactly one batch"
assert batch_ends(4, 1) == [0, 1, 2, 3], "a batch of one"
print("ok")
