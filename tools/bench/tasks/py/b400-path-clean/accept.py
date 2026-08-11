from solution import path_clean

assert path_clean("a/b/..") == "a", "the step back removes one segment"
assert path_clean("a/..") == "", "back to nothing"
assert path_clean("..") == "", "nothing to step back from"
assert path_clean("a/b") == "a/b", "no steps back at all"
assert path_clean("") == "", "an empty path"
assert path_clean("a/../b") == "b", "a step back in the middle"
print("ok")
