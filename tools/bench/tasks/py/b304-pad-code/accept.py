from solution import pad_code

assert pad_code("7", 3) == "007", "padded on the left"
assert pad_code("123", 3) == "123", "already the right width"
assert pad_code("1234", 3) == "1234", "wider than asked for"
assert pad_code("", 2) == "00", "an empty code is all padding"
assert pad_code("ab", 4) == "00ab", "letters are padded too"
assert pad_code("9", 1) == "9", "no room to pad"
print("ok")
