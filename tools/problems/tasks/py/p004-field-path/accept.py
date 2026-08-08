from solution import split_field_path

assert split_field_path("a") == ["a"], "single identifier"
assert split_field_path("items[0].tags[2]") == [
    "items",
    0,
    "tags",
    2,
], "identifiers and integer indexes interleave"
assert split_field_path("a.b.c") == ["a", "b", "c"], "dotted chain"
assert split_field_path("m[10][3]") == ["m", 10, 3], "stacked indexes"
assert split_field_path("_x9[0].y_z") == [
    "_x9",
    0,
    "y_z",
], "underscores in identifiers"
assert split_field_path("items[0].tags[2]")[1] == 0, "index is an integer"
assert not isinstance(split_field_path("m[10][3]")[1], str), "index is not text"


def rejects(value):
    try:
        split_field_path(value)
    except ValueError:
        return True
    return False


assert rejects(""), "empty string is rejected"
assert rejects(".a"), "leading dot is rejected"
assert rejects("a."), "trailing dot is rejected"
assert rejects("a[]"), "empty brackets are rejected"
assert rejects("a[3"), "unterminated bracket is rejected"
assert rejects("a[03]"), "leading zero index is rejected"
assert rejects("a[+3]"), "signed index is rejected"
assert rejects("9a"), "identifier starting with digit is rejected"
assert rejects("a..b"), "doubled dot is rejected"
assert rejects(7), "non-string is rejected"
print("ok")
