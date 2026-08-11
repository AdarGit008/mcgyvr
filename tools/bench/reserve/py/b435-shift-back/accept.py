from solution import shift_back

assert shift_back("d", 3) == "a", "three places back"
assert shift_back("a", 1) == "z", "round from the front to the end"
assert shift_back("abc", 0) == "abc", "no places at all"
assert shift_back("", 3) == "", "an empty text"
assert shift_back("a-b", 1) == "z-a", "a dash is left alone"
assert shift_back("Az", 1) == "Ay", "a capital is not a small letter"
print("ok")
