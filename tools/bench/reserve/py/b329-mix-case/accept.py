from solution import mix_case

assert mix_case("abc") == "AbC", "the letters alternate"
assert mix_case("a-b-c") == "A-b-C", "a dash does not move it along"
assert mix_case("") == "", "nothing to case"
assert mix_case("AB") == "Ab", "already-capital letters still alternate"
assert mix_case("1a2b") == "1A2b", "digits are left alone"
assert mix_case("hello") == "HeLlO", "a longer word"
print("ok")
