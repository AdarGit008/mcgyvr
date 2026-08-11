from solution import normalize_label

assert normalize_label("Alpha") == "alpha", "a clean word is lowercased"
assert normalize_label("  Team  Alpha  ") == "team-alpha", "surrounding space trims, runs collapse"
assert normalize_label("build_42_final") == "build-42-final", "underscores become hyphens"
assert normalize_label("- retry -- now -") == "retry-now", "mixed separator runs collapse"
assert normalize_label("release-2-0") == "release-2-0", "an already-clean label is unchanged"
assert normalize_label("a" * 32) == "a" * 32, "a 32-character label is allowed"


def rejects(value):
    try:
        normalize_label(value)
    except Exception:
        return True
    return False


assert rejects("a" * 33), "a 33-character label is rejected"
assert rejects("café"), "a non-ASCII character is rejected"
assert rejects("   "), "whitespace only is rejected"
assert rejects("_-_"), "separators only are rejected"
assert rejects(42), "a non-string argument is rejected"
assert rejects("  New "), "a reserved name is rejected"
print("ok")
