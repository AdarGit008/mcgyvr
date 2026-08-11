from solution import byte_hex, bytes_hex

assert byte_hex(0) == "00", "nothing is still two digits"
assert byte_hex(255) == "ff", "the largest value"
assert byte_hex(16) == "10", "the second digit rolls over"
assert bytes_hex([0, 255]) == "00ff", "two values run together"
assert bytes_hex([]) == "", "no values at all"
assert bytes_hex([1]) == "01", "one value keeps its leading zero"
print("ok")
