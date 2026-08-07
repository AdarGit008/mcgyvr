from solution import posting_lists

assert posting_lists(["The quick fox", "a fox! A FOX.", "42 x-rays 42", ""]) == {
    "the": [0],
    "quick": [0],
    "fox": [0, 1],
    "rays": [2],
}, "folds case, drops digit-only and single-character terms"
assert posting_lists(["Don't stop"]) == {
    "don": [0],
    "stop": [0],
}, "an apostrophe splits a word"
assert posting_lists(["beta", "alpha", "beta alpha"]) == {
    "beta": [0, 2],
    "alpha": [1, 2],
}, "positions ascend within each list"
assert posting_lists(["Fox fox FOX"]) == {
    "fox": [0]
}, "repeats within one document collapse"
assert posting_lists([]) == {}, "no documents, empty index"
assert posting_lists(["", "..."]) == {}, "wordless documents index nothing"


def rejects(documents):
    try:
        posting_lists(documents)
    except ValueError:
        return True
    return False


assert rejects([3]), "non-string document rejected"
assert rejects("abc"), "bare string input rejected"
print("ok")
