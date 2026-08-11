from solution import path_toll

assert path_toll(["flat", "flat", "flat"]) == 4, "the third step is free"
assert path_toll(["hill", "hill"]) == 10, "no step reaches the third"
assert path_toll(["flat", "flat", "flat", "flat"]) == 6, "counting carries on past the third"
assert path_toll(["hill", "flat", "hill", "flat"]) == 9, "kinds mixed along the path"
assert path_toll(["odd"]) == 3, "an unnamed kind takes the middle cost"
assert path_toll([]) == 0, "a path of no steps"
print("ok")
