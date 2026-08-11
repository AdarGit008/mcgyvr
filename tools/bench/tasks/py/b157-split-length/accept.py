from solution import split_length

assert split_length(0) == "0mm", "zero length reads 0mm"
assert split_length(7) == "7mm", "millimetres alone"
assert split_length(30) == "3cm", "an exact count of centimetres"
assert split_length(1000) == "1m", "an exact metre"
assert split_length(999) == "99cm 9mm", "just under a metre"
assert split_length(1005) == "1m 5mm", "a zero-count unit is skipped"
assert split_length(1234) == "1m 23cm 4mm", "all three units appear"
assert split_length(123456) == "123m 45cm 6mm", "large lengths carve the same way"


def rejects(value):
    try:
        split_length(value)
    except ValueError:
        return True
    return False


assert rejects(2.5), "a fractional length is rejected"
assert rejects("5"), "a string length is rejected"
assert rejects(True), "a boolean length is rejected"
assert rejects(-1), "a negative length is rejected"
print("ok")
