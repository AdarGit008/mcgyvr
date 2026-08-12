from solution import trim_zeros

assert trim_zeros("007") == "7", "the padding goes"
assert trim_zeros("0") == "0", "a lone zero stays"
assert trim_zeros("000") == "0", "one digit is always left"
assert trim_zeros("-0042") == "-42", "the sign stays in front"
assert trim_zeros("12x") == "12x", "not a number, untouched"
assert trim_zeros("") == "", "empty text is not a number"
assert trim_zeros("1200") == "1200", "inner zeros are not leading"
print("ok")
