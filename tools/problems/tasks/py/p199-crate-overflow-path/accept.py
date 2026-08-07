from solution import crate_overflow_path


def crate(tag, weight, cap, inside=None):
    return {
        "tag": tag,
        "weight": weight,
        "cap": cap,
        "inside": [] if inside is None else inside,
    }


def rejects(root):
    try:
        crate_overflow_path(root)
    except ValueError:
        return True
    return False


assert crate_overflow_path(crate("box", 3, 5)) == "", "a light lone crate sits fine"
assert crate_overflow_path(crate("box", 5, 5)) == "", "exactly on the cap is fine"
assert crate_overflow_path(crate("box", 9, 5)) == "box", "a lone crate can spill"

assert (
    crate_overflow_path(crate("ship", 1, 100, [crate("a", 2, 10), crate("b", 3, 10)]))
    == ""
), "a roomy nesting spills nowhere"

assert (
    crate_overflow_path(crate("ship", 1, 100, [crate("a", 20, 10)])) == "ship.a"
), "a packed crate over its own cap is named with its trail"

assert (
    crate_overflow_path(crate("ship", 5, 6, [crate("a", 2, 10)])) == "ship"
), "the outer crate carries the weight of what it holds"

assert (
    crate_overflow_path(crate("r", 1, 2, [crate("m", 1, 10, [crate("z", 1, 10)])]))
    == "r"
), "gross rolls up through every level"

assert (
    crate_overflow_path(crate("r", 0, 50, [crate("m", 0, 50, [crate("z", 99, 50)])]))
    == "r.m.z"
), "a trail three deep"

assert (
    crate_overflow_path(
        crate(
            "r",
            0,
            5,
            [crate("a", 0, 10, [crate("a1", 99, 10)]), crate("b", 99, 1)],
        )
    )
    == "r.a.a1"
), "the earlier branch is searched to the bottom first"

assert rejects([1, 2]), "an outermost crate that is not a mapping is rejected"
assert rejects(crate("", 1, 5)), "an empty tag is rejected"
assert rejects(crate("a.b", 1, 5)), "a tag carrying a full stop is rejected"
assert rejects(
    crate("r", 0, 5, [crate("twin", 1, 5), crate("twin", 1, 5)])
), "two crates side by side sharing a tag are rejected"
assert rejects(crate("r", -1, 5)), "a negative weight is rejected"
assert rejects(crate("r", 1, 0)), "a cap of zero is rejected"
assert rejects(
    {"tag": "r", "weight": 1, "cap": 5, "inside": "none"}
), "an inside that is not a list is rejected"

print("ok")
