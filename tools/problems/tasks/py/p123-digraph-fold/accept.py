from solution import fold_digraphs

assert fold_digraphs("ab", [["a", "b"], ["b", "c"]]) == "bc", (
    "one pair's output never feeds another pair"
)
assert fold_digraphs("chip", [["c", "k"], ["ch", "x"]]) == "xip", (
    "the widest pattern wins regardless of table order"
)
assert fold_digraphs("aaa", [["a", "1"], ["aa", "2"]]) == "21", (
    "widest match at every position"
)
assert fold_digraphs("sos", [["s", "ss"]]) == "ssoss", "emitted output is final"
assert fold_digraphs("x", [["x", "1"], ["x", "2"]]) == "1", (
    "width tie goes to the earlier pair"
)
assert fold_digraphs("mud", [["zz", "q"]]) == "mud", "unclaimed positions copy"
assert fold_digraphs("", [["a", "b"]]) == "", "empty text"
assert fold_digraphs("th", [["th", "h"]]) == "h", "output may echo a pattern"


def rejects(text, table):
    try:
        fold_digraphs(text, table)
    except ValueError:
        return True
    return False


assert rejects("x", [["", "y"]]), "empty pattern is rejected"
print("ok")
