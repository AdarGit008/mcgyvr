from solution import merge_markup

assert merge_markup([]) == [], "no spans"
assert merge_markup([{"start": 3, "end": 8, "tag": "name"}]) == [
    [3, 8, "name"]
], "single span"
assert merge_markup(
    [{"start": 5, "end": 9, "tag": "date"}, {"start": 0, "end": 5, "tag": "date"}]
) == [[0, 9, "date"]], "touching same-tag spans collapse"
assert merge_markup(
    [
        {"start": 6, "end": 10, "tag": "q"},
        {"start": 0, "end": 4, "tag": "q"},
        {"start": 3, "end": 7, "tag": "q"},
    ]
) == [[0, 10, "q"]], "a chain of same-tag overlaps collapses transitively"
assert merge_markup(
    [
        {"start": 4, "end": 6, "tag": "b"},
        {"start": 0, "end": 4, "tag": "a"},
        {"start": 6, "end": 9, "tag": "a"},
    ]
) == [
    [0, 4, "a"],
    [4, 6, "b"],
    [6, 9, "a"],
], "different tags may touch, output sorted by start"
assert merge_markup(
    [{"start": 0, "end": 3, "tag": "x"}, {"start": 10, "end": 12, "tag": "x"}]
) == [[0, 3, "x"], [10, 12, "x"]], "distant same-tag spans stay separate"


def rejects(spans):
    try:
        merge_markup(spans)
    except ValueError:
        return True
    return False


assert rejects(
    [{"start": 0, "end": 5, "tag": "a"}, {"start": 4, "end": 9, "tag": "b"}]
), "different tags sharing a position is an error"
assert rejects(
    [
        {"start": 0, "end": 2, "tag": "a"},
        {"start": 1, "end": 3, "tag": "a"},
        {"start": 2, "end": 4, "tag": "b"},
    ]
), "the conflict check runs against the collapsed spans"
assert rejects([{"start": 0.5, "end": 2, "tag": "a"}]), "non-integer bound is rejected"
assert rejects([{"start": -1, "end": 2, "tag": "a"}]), "negative start is rejected"
assert rejects([{"start": 3, "end": 3, "tag": "a"}]), "empty span is rejected"
assert rejects([{"start": 0, "end": 2, "tag": ""}]), "empty tag is rejected"
print("ok")
