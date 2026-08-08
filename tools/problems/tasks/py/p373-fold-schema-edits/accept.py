from solution import fold_schema_edits

assert fold_schema_edits(["one", "two"], []) == ["one", "two"], "no edits changes nothing"
assert fold_schema_edits(["one", "two"], [{"op": "add", "field": "three"}]) == [
    "one",
    "two",
    "three",
], "an add hangs on the end"
assert fold_schema_edits(["one", "two", "three"], [{"op": "drop", "field": "two"}]) == [
    "one",
    "three",
], "a drop closes the gap behind it"
assert fold_schema_edits(["one", "two"], [{"op": "rename", "field": "one", "into": "first"}]) == [
    "first",
    "two",
], "a rename holds its place"
assert fold_schema_edits(
    ["one", "two"],
    [{"op": "drop", "field": "two"}, {"op": "add", "field": "two"}],
) == ["one", "two"], "a heading freed by a drop may be added again"
assert fold_schema_edits(
    ["one", "two"],
    [{"op": "drop", "field": "one"}, {"op": "rename", "field": "two", "into": "one"}],
) == ["one"], "a rename may take over a freed heading"
assert fold_schema_edits(["one"], [{"op": "drop", "field": "one"}]) == [], "the header may run empty"


def rejects(fields, edits):
    try:
        fold_schema_edits(fields, edits)
    except ValueError:
        return True
    return False


assert rejects(
    ["one"], [{"op": "add", "field": "two"}, {"op": "add", "field": "two"}]
), "a heading brought in by an add may not be added twice"
assert rejects(
    ["one"],
    [{"op": "add", "field": "two"}, {"op": "rename", "field": "one", "into": "two"}],
), "a rename may not take over a heading an add brought in"
assert rejects(["one", "two"], [{"op": "add", "field": "one"}]), "add on a live heading is refused"
assert rejects(["one", "two"], [{"op": "rename", "field": "one", "into": "two"}]), "rename onto a live heading is refused"
assert rejects(["one"], [{"op": "drop", "field": "gone"}]), "drop of an absent heading is refused"
assert rejects(["one"], [{"op": "shuffle", "field": "one"}]), "an unknown op is refused"
assert rejects(["one"], [{"op": "rename", "field": "one", "into": ""}]), "an empty into is refused"
assert rejects(["one", "one"], []), "a repeat among the headings handed in is refused"
assert rejects([], []), "an empty header is refused"
assert rejects(["one"], [42]), "an edit that is not a mapping is refused"
print("ok")
