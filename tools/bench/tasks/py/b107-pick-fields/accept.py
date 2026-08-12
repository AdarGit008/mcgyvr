from solution import pick_fields


def rejects(records, fields):
    try:
        pick_fields(records, fields)
    except Exception:
        return True
    return False


assert pick_fields(
    [{"name": "ada", "role": "pilot"}, {"name": "vi", "role": "nav"}],
    ["name", "role"],
) == [["ada", "pilot"], ["vi", "nav"]], "one row per record in field order"
assert pick_fields([{"a": 1, "b": 2}], ["b", "a"]) == [
    [2, 1]
], "the field list, not the record, orders the row"
assert pick_fields([{"name": "ada", "nick": "ace"}], ["name", "nick?"]) == [
    ["ada", "ace"]
], "a present optional field reads its value"
assert pick_fields([{"name": "vi"}], ["name", "nick?"]) == [
    ["vi", None]
], "an absent optional field reads as None"
assert pick_fields([], ["name"]) == [], "no records, no rows"
assert pick_fields([{"n": 0, "s": ""}], ["n", "s"]) == [
    [0, ""]
], "falsy values pass through untouched"
assert rejects("crew", ["name"]), "records must be a list"
assert rejects([7], ["name"]), "a record must be a mapping"
assert rejects([], []), "an empty field list is rejected"
assert rejects([], [7]), "a field name must be a string"
assert rejects([], ["?"]), "a bare marker has no stem"
assert rejects([], ["id", "id"]), "a repeated field is rejected"
assert rejects([], ["id", "id?"]), "optional and required twins share a stem"
assert rejects([{"a": 1}], ["b"]), "a missing required field is rejected"
print("ok")
