from solution import badge_runs


def rejects(value):
    try:
        badge_runs(value)
    except Exception:
        return True
    return False


assert badge_runs("AAAB") == "A3B1", "a long run then a single"
assert badge_runs("A") == "A1", "a lone letter still carries its count"
assert badge_runs("AB") == "A1B1", "two singles"
assert badge_runs("AABBA") == "A2B2A1", "a letter may return later"
assert badge_runs("ZZZZ") == "Z4", "one run spanning the whole string"
assert rejects(""), "the empty string is rejected"
print("ok")
