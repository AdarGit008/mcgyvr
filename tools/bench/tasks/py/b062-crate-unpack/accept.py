from solution import crate_depth, unpack_crates

assert unpack_crates([]) == [], "an empty crate unpacks to nothing"
assert unpack_crates(["bolts", "nuts"]) == ["bolts", "nuts"], "a flat crate keeps its order"
assert unpack_crates(["tape", ["glue", "twine"], "shears"]) == [
    "tape",
    "glue",
    "twine",
    "shears",
], "a nested crate unpacks in place"
assert unpack_crates([["clips", ["pins"]], "labels"]) == [
    "clips",
    "pins",
    "labels",
], "deep nesting unpacks depth first"
assert unpack_crates(["felt", [], "cord"]) == ["felt", "cord"], "an empty inner crate adds nothing"


def rejects(crate):
    try:
        unpack_crates(crate)
    except Exception:
        return True
    return False


assert rejects(["felt", 3]), "a numeric entry is rejected"
assert rejects([""]), "an empty name is rejected"
assert rejects(["felt", [None]]), "an invalid nested entry is rejected"
assert crate_depth(["felt", "cord"]) == 1, "a flat crate has depth 1"
assert crate_depth(["a", ["b", ["c"]]]) == 3, "each nesting level adds one"
print("ok")
