from solution import trim_caption

assert trim_caption("on time", 20) == "on time", "short text is unchanged"
assert trim_caption("exact fit", 9) == "exact fit", "text at exactly the limit is unchanged"
assert trim_caption("the quick brown fox", 10) == "the quick…", "a cut at a word boundary keeps the word"
assert trim_caption("the quick brown fox", 12) == "the quick…", "a mid-word cut drops back to the last space"
assert trim_caption("extraordinary", 6) == "extra…", "a first word too long is cut short"
assert trim_caption("ab   cdef", 6) == "ab…", "hanging spaces are removed before the ellipsis"


def rejects(*args):
    try:
        trim_caption(*args)
    except ValueError:
        return True
    return False


assert rejects(42, 5), "non-string text is rejected"
assert rejects("hello world", 0), "a zero limit is rejected"
assert rejects("hello world", 2.5), "a fractional limit is rejected"
print("ok")
