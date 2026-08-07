from solution import rank_candidates

pool = ["Prelude", "preload", "PRE", "espresso", "spread", "grep"]
assert rank_candidates(pool, "pre", 10) == [
    "PRE",
    "Prelude",
    "preload",
    "spread",
    "espresso",
], "exact, then prefixes in original order, then infixes by length"
assert rank_candidates(pool, "pre", 3) == [
    "PRE",
    "Prelude",
    "preload",
], "limit truncates the ranking"
assert rank_candidates(pool, "PrE", 10) == [
    "PRE",
    "Prelude",
    "preload",
    "spread",
    "espresso",
], "query case never matters"
assert rank_candidates(["alpha", "beta"], "zzz", 5) == [], "no candidate contains the query"
assert rank_candidates(["log", "dialog", "logger", "blog"], "log", 10) == [
    "log",
    "logger",
    "blog",
    "dialog",
], "shorter infix beats longer infix"
assert rank_candidates(["ab", "xab", "AB"], "ab", 10) == [
    "ab",
    "AB",
    "xab",
], "equal-length exact matches keep list order and infix follows"


def rejects(*args):
    try:
        rank_candidates(*args)
    except ValueError:
        return True
    return False


assert rejects(pool, "", 3), "empty query is rejected"
assert rejects(pool, 7, 3), "non-string query is rejected"
assert rejects(pool, "pre", 0), "zero limit is rejected"
assert rejects(["ok", 5], "o", 3), "non-string candidate is rejected"
print("ok")
