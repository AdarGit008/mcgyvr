from solution import flip_channels

assert flip_channels(0, 0, 0) == 1, "flipping channel zero of a dark board lights it"
assert flip_channels(0, 0, 15) == 65535, "flipping every channel of a dark board lights the board"
assert flip_channels(65535, 0, 15) == 0, "flipping every channel of a lit board darkens it"
assert flip_channels(10, 1, 2) == 12, "a two-channel span flips only its own bits"
assert flip_channels(1, 4, 7) == 241, "channels outside the span keep their state"
assert flip_channels(flip_channels(37, 3, 9), 3, 9) == 37, "flipping a span twice restores the word"


def rejects(word, lo, hi):
    try:
        flip_channels(word, lo, hi)
    except Exception:
        return True
    return False


assert rejects(3.5, 0, 1), "a fractional word is rejected"
assert rejects(65536, 0, 1), "a word beyond 16 bits is rejected"
assert rejects(7, -1, 3), "a negative bound is rejected"
assert rejects(7, 3, 16), "a bound past channel 15 is rejected"
assert rejects(7, 9, 3), "a lo greater than hi is rejected"
print("ok")
