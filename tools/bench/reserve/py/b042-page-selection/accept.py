from solution import expand_selection, read_span

assert read_span("4-6") == [4, 6], "a dashed piece keeps both ends"
assert expand_selection("3") == [3], "one page expands to itself"
assert expand_selection("1-3,7,10-12") == [1, 2, 3, 7, 10, 11, 12], "spans and lone pages mix"
assert expand_selection("4,5-6") == [4, 5, 6], "touching pieces are allowed"


def rejects(value):
    try:
        expand_selection(value)
    except Exception:
        return True
    return False


assert rejects(""), "an empty selection is rejected"
assert rejects("5-2"), "a backwards span is rejected"
assert rejects("1-4,3-6"), "an overlapping piece is rejected"
assert rejects("2,,5"), "an empty piece is rejected"
assert rejects(7), "a non-string selection is rejected"
print("ok")
