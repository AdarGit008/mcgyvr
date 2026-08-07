from solution import word_span_starts

assert word_span_starts("The cat sat. THE CAT sat again.", "the cat") == [
    0,
    13,
], "case-insensitive hits at original offsets"
assert word_span_starts("do do do", "do do") == [0, 3], "overlapping hits"
assert word_span_starts("please re-run all re-run jobs", "re run") == [
    7,
    18,
], "a hyphen splits words the same way a space does"
assert (
    word_span_starts("concatenate cats", "cat") == []
), "never matches inside a longer word"
assert word_span_starts("The cat sat. THE CAT sat again.", "sat, again!") == [
    21
], "punctuation inside the query is only a separator"
assert word_span_starts("", "cat") == [], "empty passage has no hits"
assert word_span_starts("v2 build v2 ship", "V2") == [0, 9], "digits belong to words"


def rejects(passage, query):
    try:
        word_span_starts(passage, query)
    except ValueError:
        return True
    return False


assert rejects("text", "!!!"), "wordless query rejected"
assert rejects("text", 5), "non-string query rejected"
assert rejects(None, "cat"), "non-string passage rejected"
print("ok")
