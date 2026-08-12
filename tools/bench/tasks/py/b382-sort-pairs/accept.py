from solution import field_of, sort_pairs


def rejects(record, field):
    try:
        field_of(record, field)
    except Exception:
        return True
    return False


assert field_of({"age": 3}, "age") == 3, "the field is read"
assert sort_pairs([{"age": 3}, {"age": 1}], "age") == [
    {"age": 1},
    {"age": 3},
], "ordered by the field"
assert sort_pairs([], "age") == [], "no records at all"
assert sort_pairs([{"age": 2}], "age") == [{"age": 2}], "a single record"
assert sort_pairs([{"age": 1, "id": 1}, {"age": 1, "id": 2}], "age") == [
    {"age": 1, "id": 1},
    {"age": 1, "id": 2},
], "a tie keeps the earlier record earlier"
assert rejects({"age": 3}, "name"), "a missing field is rejected"
print("ok")
