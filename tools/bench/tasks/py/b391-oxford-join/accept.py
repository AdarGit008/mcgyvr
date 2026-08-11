from solution import oxford_join

assert oxford_join(["a", "b", "c"]) == "a, b and c", "three names"
assert oxford_join(["a", "b"]) == "a and b", "two names take no comma"
assert oxford_join(["a"]) == "a", "one name stands alone"
assert oxford_join([]) == "", "no names at all"
assert oxford_join(["a", "b", "c", "d"]) == "a, b, c and d", "four names"
assert oxford_join(["x", "y"]) == "x and y", "another pair"
print("ok")
