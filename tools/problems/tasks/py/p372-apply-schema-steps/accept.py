from solution import apply_schema_steps

base = [
    {"name": "id", "kind": "int"},
    {"name": "label", "kind": "text"},
]

assert apply_schema_steps(base, []) == [
    {"name": "id", "kind": "int"},
    {"name": "label", "kind": "text"},
], "an empty step list leaves the table as it was"

assert apply_schema_steps(base, [{"op": "add", "name": "seen_at", "kind": "long"}]) == [
    {"name": "id", "kind": "int"},
    {"name": "label", "kind": "text"},
    {"name": "seen_at", "kind": "long"},
], "an add lands at the end"

assert base == [
    {"name": "id", "kind": "int"},
    {"name": "label", "kind": "text"},
], "the argument is left untouched"

assert apply_schema_steps(
    [
        {"name": "a1", "kind": "int"},
        {"name": "b2", "kind": "int"},
        {"name": "c3", "kind": "long"},
    ],
    [{"op": "drop", "name": "b2"}],
) == [
    {"name": "a1", "kind": "int"},
    {"name": "c3", "kind": "long"},
], "a drop closes the gap behind it"

assert apply_schema_steps(base, [{"op": "rename", "name": "id", "to": "row_key"}]) == [
    {"name": "row_key", "kind": "int"},
    {"name": "label", "kind": "text"},
], "a rename keeps place and kind"

assert apply_schema_steps(base, [{"op": "retype", "name": "id", "kind": "long"}]) == [
    {"name": "id", "kind": "long"},
    {"name": "label", "kind": "text"},
], "int widens to long"

assert apply_schema_steps(
    base,
    [
        {"op": "drop", "name": "label"},
        {"op": "add", "name": "label", "kind": "long"},
        {"op": "retype", "name": "label", "kind": "text"},
        {"op": "rename", "name": "id", "to": "label2"},
    ],
) == [
    {"name": "label2", "kind": "int"},
    {"name": "label", "kind": "text"},
], "a freed name may be taken again later in the run"

assert apply_schema_steps(base, [{"op": "retype", "name": "id", "kind": "text"}]) == [
    {"name": "id", "kind": "text"},
    {"name": "label", "kind": "text"},
], "int may skip straight to text"


def rejects(columns, steps):
    try:
        apply_schema_steps(columns, steps)
    except ValueError:
        return True
    return False


assert rejects([], []), "an empty table is refused"
assert rejects(base, [{"op": "add", "name": "id", "kind": "int"}]), "add on a taken name is refused"
assert rejects(base, [{"op": "drop", "name": "gone"}]), "drop of an absent column is refused"
assert rejects([{"name": "only", "kind": "int"}], [{"op": "drop", "name": "only"}]), "the last column may not be dropped"
assert rejects(base, [{"op": "rename", "name": "id", "to": "label"}]), "rename onto a taken name is refused"
assert rejects(base, [{"op": "rename", "name": "id", "to": "id"}]), "rename onto its own name is refused"
assert rejects(base, [{"op": "retype", "name": "label", "kind": "int"}]), "a narrowing retype is refused"
assert rejects(base, [{"op": "retype", "name": "id", "kind": "int"}]), "a retype to the held kind is refused"
assert rejects(base, [{"op": "widen", "name": "id", "kind": "text"}]), "an unknown op is refused"
assert rejects(base, [{"op": "add", "name": "Bad", "kind": "int"}]), "a name of the wrong shape is refused"
assert rejects(base, [{"op": "add", "name": "ok_name", "kind": "blob"}]), "an unknown kind is refused"
assert rejects([{"name": "x", "kind": "int"}, {"name": "x", "kind": "text"}], []), "a repeated column name is refused"
assert rejects(base, [None]), "a step that is not a mapping is refused"
assert rejects("nope", []), "a table that is not a list is refused"
print("ok")
