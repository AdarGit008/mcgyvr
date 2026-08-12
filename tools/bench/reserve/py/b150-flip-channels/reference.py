def flip_channels(word, lo, hi):
    if not isinstance(word, int) or word < 0 or word > 65535:
        raise ValueError("word must be an integer from 0 to 65535")
    for bound in (lo, hi):
        if not isinstance(bound, int) or bound < 0 or bound > 15:
            raise ValueError("channel bounds must be integers from 0 to 15")
    if lo > hi:
        raise ValueError("lo must not exceed hi")
    span = ((1 << (hi - lo + 1)) - 1) << lo
    return word ^ span
