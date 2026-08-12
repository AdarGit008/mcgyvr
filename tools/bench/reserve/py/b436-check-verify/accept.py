from solution import check_verify

assert check_verify("1234") is True, "the digits reach a multiple of ten"
assert check_verify("1235") is False, "one digit out"
assert check_verify("0") is True, "a nought checks out"
assert check_verify("5") is False, "a lone five does not"
assert check_verify("55") is True, "two fives make ten"
assert check_verify("9991") is False, "twenty-eight is not a multiple of ten"
print("ok")
