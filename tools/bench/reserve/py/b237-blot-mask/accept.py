from solution import blot_mask

assert blot_mask("ABCD1234") == "****1234", "the tail stays readable"
assert blot_mask("ABCDE") == "*BCDE", "one character masked"
assert blot_mask("ABCD") == "ABCD", "exactly four is untouched"
assert blot_mask("AB") == "AB", "shorter than four is untouched"
assert blot_mask("") == "", "an empty code is untouched"
assert blot_mask("1234567890") == "******7890", "a long code"
print("ok")
