from solution import outline_diff

assert outline_diff({}, {}) == [], "empty outlines"

assert outline_diff({"a": {}}, {"a": {}}) == [], "identical outlines"

assert outline_diff({}, {"b": {}, "a": {}}) == [
    "added a",
    "added b",
], "top-level adds come out sorted"

assert outline_diff(
    {"ch1": {"intro": {}}}, {"ch1": {"intro": {}, "notes": {}}}
) == ["added ch1/notes"], "shared headings are descended into"

assert outline_diff({"ch1": {"old": {"deep": {}}}}, {"ch1": {}}) == [
    "removed ch1/old"
], "a removed branch is exactly one line"

assert outline_diff(
    {"a": {"x": {}}, "b": {}}, {"a": {"y": {}}, "c": {}}
) == [
    "added a/y",
    "added c",
    "removed a/x",
    "removed b",
], "mixed nested adds and removes, sorted"

print("ok")
