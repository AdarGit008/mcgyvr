from solution import top_load

assert top_load(["wood", "wood", "steel"]) == "steel", "one heavy item outweighs two lighter"
assert top_load(["wood", "wood", "wood", "steel"]) == "wood", "three lighter items outweigh one heavy"
assert top_load(["wood", "steel", "wood"]) == "steel", "items of a kind counted together"
assert top_load(["a", "b"]) == "a", "kinds of a weight name the earliest"
assert top_load(["steel"]) == "steel", "a load of one item"
assert top_load([]) == "", "a load of nothing"
print("ok")
