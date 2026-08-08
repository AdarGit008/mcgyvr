from solution import decode_frames

assert decode_frames([]) == [], "an empty stream holds no frames"
assert decode_frames([0, 3, 1, 2, 3, 0]) == [
    [1, 2, 3]
], "a single frame with a correct XOR trailer"
assert decode_frames([0, 0, 0, 0, 2, 5, 9, 12]) == [
    [],
    [5, 9],
], "a zero-length frame followed by a two-byte frame"

big_payload = [7] * 258
assert decode_frames([1, 2] + big_payload + [0]) == [
    big_payload
], "the header is big-endian: 0x0102 is 258, not 513"


def rejects(stream):
    try:
        decode_frames(stream)
    except ValueError:
        return True
    return False


assert rejects([0, 1, 5, 4]), "a wrong trailer is rejected"
assert rejects([0]), "a lone header byte is rejected"
assert rejects([0, 5, 1, 2]), "a stream ending inside a payload is rejected"
assert rejects([0, 2, 1, 2]), "a frame missing its trailer is rejected"
assert rejects([0, 0, 0, 9]), "trailing garbage after a good frame is rejected"
assert rejects([0, 1, 256, 0]), "256 is not a byte"
assert rejects([0, 1, -1, 255]), "-1 is not a byte"
assert rejects([0, 1, 1.5, 0]), "a fraction is not a byte"
print("ok")
