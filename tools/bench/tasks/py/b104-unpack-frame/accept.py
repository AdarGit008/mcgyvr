from solution import unpack_frame

assert unpack_frame([0, 0]) == [], "a zero-reading frame is header and trailer"
assert unpack_frame([1, 150, 1, 152]) == [150], "a two-byte varint decodes"
assert unpack_frame([2, 0, 172, 2, 176]) == [
    0,
    300,
], "two readings come back in order"
assert unpack_frame([1, 128, 1, 130]) == [
    128
], "the first two-byte value has a zero low group"
assert unpack_frame([1, 127, 128]) == [127], "the largest one-byte value"
assert unpack_frame([1, 255, 255, 255, 255, 127, 124]) == [
    34359738367
], "a five-byte varint carries 35 bits"


def rejects(data):
    try:
        unpack_frame(data)
    except ValueError:
        return True
    return False


assert rejects("frame"), "a non-list is rejected"
assert rejects([256]), "a byte past 255 is rejected"
assert rejects([]), "an empty frame has no header"
assert rejects([1, 150]), "a frame ending inside a varint"
assert rejects([1, 5]), "a frame with no room for a trailer"
assert rejects([0, 0, 9]), "bytes after the trailer"
assert rejects([1, 150, 0, 151]), "a wasted final zero byte"
assert rejects([1, 255, 255, 255, 255, 255, 1, 0]), "a six-byte varint is rejected"
assert rejects([1, 5, 7]), "a trailer that misses the sum"
print("ok")
