from solution import trim_to


def rejects(line, limit):
    try:
        trim_to(line, limit)
    except Exception:
        return True
    return False


assert trim_to("abcdefgh", 5) == "ab...", "the dots count toward the limit"
assert trim_to("abc", 5) == "abc", "already short enough"
assert trim_to("abcde", 5) == "abcde", "exactly on the limit"
assert trim_to("abcdef", 5) == "ab...", "one over the limit"
assert trim_to("", 10) == "", "an empty line"
assert rejects("abc", 3), "a limit under four is rejected"
print("ok")
