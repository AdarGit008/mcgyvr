from solution import count_phrase

assert count_phrase(["the", "cat", "sat"], "cat") == 1, "one plain hit"
assert count_phrase(["the", "catalog", "sat"], "cat") == 0, (
    "a longer word is not a hit"
)
assert count_phrase(["The", "CAT", "sat"], "cat") == 1, "token case is ignored"
assert count_phrase(["cat"], "Cat") == 1, "phrase case is ignored too"
assert count_phrase(["big", "dog", "big", "dog"], "big dog") == 2, (
    "two separate hits"
)
assert count_phrase(["a", "a", "a"], "a a") == 1, "overlapping hits count once"
assert count_phrase(["big", "dog", "dog"], "big dog") == 1, (
    "a trailing token does not double count"
)
assert count_phrase(["one", "two"], "three") == 0, "no hit at all"
assert count_phrase([], "x") == 0, "no tokens, no hits"


def rejects(tokens, phrase):
    try:
        count_phrase(tokens, phrase)
    except ValueError:
        return True
    return False


assert rejects(["a"], ""), "empty phrase rejected"
assert rejects(["a"], "   "), "blank phrase rejected"
print("ok")
