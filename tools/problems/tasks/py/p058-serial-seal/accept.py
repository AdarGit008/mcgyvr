from solution import seal_serial

assert seal_serial("00000000") == "000000000", "all zeros seal with 0"
assert seal_serial("12345678") == "123456787", "ascending digits seal with 7"
assert seal_serial("99999999") == "999999992", "all nines seal with 2"
assert seal_serial("70000000") == "70000000K", "a remainder of ten seals as the letter K"
assert seal_serial("00000001") == "000000017", "the eighth position carries weight 7"
assert seal_serial("10203040") == "102030405", "interleaved zeros"


def rejects(value):
    try:
        seal_serial(value)
    except ValueError:
        return True
    return False


assert rejects("1234567"), "seven digits are rejected"
assert rejects("123456789"), "nine digits are rejected"
assert rejects("1234567a"), "a letter is rejected"
assert rejects("1234 567"), "a space is rejected"
assert rejects(12345678), "a number is rejected"
print("ok")
