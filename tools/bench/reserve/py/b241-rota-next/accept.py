from solution import rota_next

assert rota_next(["a", "b", "c"], "a") == "b", "the next name in order"
assert rota_next(["a", "b", "c"], "b") == "c", "onward through the rota"
assert rota_next(["a", "b", "c"], "c") == "a", "the last name comes round"
assert rota_next(["solo"], "solo") == "solo", "a rota of one follows itself"
assert rota_next(["a", "b"], "z") == "z", "a name not on the rota"
assert rota_next([], "x") == "x", "an empty rota changes nothing"
print("ok")
