from solution import swap_case

assert swap_case("aB") == "Ab", "both letters turn"
assert swap_case("abc") == "ABC", "lower becomes upper"
assert swap_case("ABC") == "abc", "upper becomes lower"
assert swap_case("") == "", "nothing to turn"
assert swap_case("a1B") == "A1b", "a digit is left alone"
assert swap_case("Hello") == "hELLO", "a whole word turns"
print("ok")
