from solution import write_senary_tail

assert write_senary_tail(0, 1) == "0", "an empty reading is a single zero mark"
assert write_senary_tail(1, 2) == "3", "a half is three sixths"
assert write_senary_tail(1, 3) == "2", "a third is two sixths"
assert write_senary_tail(1, 4) == "13", "a quarter needs two marks"
assert write_senary_tail(3, 4) == "43", "three quarters"
assert write_senary_tail(5, 6) == "5", "five sixths is the largest single mark"
assert write_senary_tail(1, 36) == "01", "a leading zero mark before the last one"
assert write_senary_tail(35, 36) == "55", "the highest reading below one at that spacing"
assert write_senary_tail(1, 8) == "043", "three marks, none of them fenced"
assert write_senary_tail(1, 216) == "001", "two zero marks then a one"
assert write_senary_tail(1, 5) == "|1|", "a single mark repeating from the very start"
assert write_senary_tail(1, 7) == "|05|", "a two mark run repeating from the start"
assert write_senary_tail(2, 7) == "|14|", "the same spacing at a different reading"
assert write_senary_tail(7, 10) == "4|1|", "one settled mark ahead of the fence"
assert write_senary_tail(1, 10) == "0|3|", "a settled zero mark ahead of the fence"
assert write_senary_tail(1, 11) == "|0313452421|", "a ten mark run"
assert write_senary_tail(13, 18) == "42", "a reading that comes to rest quickly"


def rejects(numerator, denominator):
    try:
        write_senary_tail(numerator, denominator)
    except ValueError:
        return True
    return False


assert rejects(1, 0), "a lower reading of zero"
assert rejects(1, 10001), "a lower reading past the ceiling"
assert rejects(-1, 5), "an upper reading below zero"
assert rejects(5, 5), "an upper reading equal to the lower one"
assert rejects(7, 5), "an upper reading above the lower one"
assert rejects(1.5, 5), "a fractional upper reading"
assert rejects(1, 5.5), "a fractional lower reading"
assert rejects("1", 5), "an upper reading that is text"
print("ok")
