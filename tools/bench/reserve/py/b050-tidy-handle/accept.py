from solution import normalize_handle

assert normalize_handle("Dev Team") == "dev-team", "a space becomes a hyphen"
assert normalize_handle("  Big  Cat ") == "big-cat", "trims and collapses a space run"
assert normalize_handle("user_01-beta") == "user-01-beta", "underscores and hyphens unify"
assert normalize_handle("a _- b") == "a-b", "a mixed separator run is one hyphen"
assert normalize_handle("abcde_fghij_klmno_pq") == "abcde-fghij-klmno-pq", "twenty characters pass"


def rejects(value):
    try:
        normalize_handle(value)
    except ValueError:
        return True
    return False


assert rejects(42), "non-string is rejected"
assert rejects("   "), "whitespace-only is rejected"
assert rejects("dev!team"), "an illegal character is rejected"
assert rejects("-devs"), "a leading hyphen is rejected"
assert rejects("ab"), "two characters are too short"
assert rejects("abcdefghij0abcdefghij"), "twenty-one characters are too long"
print("ok")
