from solution import cipher_shift

assert cipher_shift("abc", 1) == "bcd", "each letter moves one on"
assert cipher_shift("xyz", 3) == "abc", "the end runs back to the start"
assert cipher_shift("z", 1) == "a", "the last letter wraps"
assert cipher_shift("a b", 1) == "b c", "a space is left alone"
assert cipher_shift("Hello", 1) == "Hfmmp", "a capital is left alone"
assert cipher_shift("abc", 0) == "abc", "a step of nothing changes nothing"
assert cipher_shift("", 5) == "", "an empty text"
print("ok")
