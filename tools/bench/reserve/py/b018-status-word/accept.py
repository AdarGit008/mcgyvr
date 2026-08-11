from solution import decode_status_word

assert decode_status_word(0) == {
    "channel": 0,
    "reading": 0,
    "stale": False,
}, "the all-zero word decodes to zeros"
assert decode_status_word(0x3191) == {
    "channel": 3,
    "reading": 100,
    "stale": False,
}, "a plain positive reading"
assert decode_status_word(0xF7FE) == {
    "channel": 15,
    "reading": 511,
    "stale": True,
}, "the largest channel and reading, stale"
assert decode_status_word(0x7FFD) == {
    "channel": 7,
    "reading": -1,
    "stale": False,
}, "all reading bits set decodes to minus one"
assert decode_status_word(0x1803) == {
    "channel": 1,
    "reading": -512,
    "stale": True,
}, "the most negative reading"
assert decode_status_word(0x9401) == {
    "channel": 9,
    "reading": 256,
    "stale": False,
}, "the sign bit alone is still positive at 256"
assert decode_status_word(0x5B52) == {
    "channel": 5,
    "reading": -300,
    "stale": True,
}, "a negative mid-range reading, stale"
assert decode_status_word(0x2007) == {
    "channel": 2,
    "reading": 1,
    "stale": True,
}, "a one-count reading with parity set"


def rejects(word):
    try:
        decode_status_word(word)
    except Exception:
        return True
    return False


assert rejects(0x3190), "odd parity is rejected"
assert rejects(0xF7FF), "odd parity near the top"
assert rejects(-1), "a negative word is rejected"
assert rejects(65536), "a 17-bit word is rejected"
assert rejects(2.5), "a fractional word is rejected"
assert rejects(True), "a boolean word is rejected"
assert rejects("0x3191"), "a string word is rejected"
print("ok")
