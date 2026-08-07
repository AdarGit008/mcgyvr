from solution import decode_varints

assert decode_varints([]) == [], "empty input decodes to nothing"
assert decode_varints([0]) == [0], "single zero byte"
assert decode_varints([1, 127]) == [1, 127], "two one-byte varints"
assert decode_varints([150, 1]) == [150], "continuation bit spans bytes"
assert decode_varints([5, 150, 1, 0]) == [5, 150, 0], "mixed lengths back to back"
assert decode_varints([172, 2]) == [300], "seven-bit groups accumulate"
assert decode_varints([255, 255, 3]) == [65535], "sixteen-bit maximum"
assert decode_varints([128, 128, 128, 1]) == [2097152], "four-byte varint"


def rejects(value):
    try:
        decode_varints(value)
    except ValueError:
        return True
    return False


assert rejects([128]), "lone continuation byte is rejected"
assert rejects([150]), "truncated after high bit is rejected"
assert rejects([1, 128]), "truncated at list end is rejected"
assert rejects([128, 0]), "overlong encoding of zero is rejected"
assert rejects([256]), "byte above 255 is rejected"
assert rejects([-1]), "negative byte is rejected"
assert rejects([1.5]), "fractional byte is rejected"
assert rejects("bytes"), "non-list is rejected"
print("ok")
