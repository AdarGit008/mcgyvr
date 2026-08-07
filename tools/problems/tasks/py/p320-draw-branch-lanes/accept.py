from solution import draw_branch_lanes


def of(pairs):
    return [{"id": name, "branch": branch} for name, branch in pairs]


def rejects(entries):
    try:
        draw_branch_lanes(entries)
    except ValueError:
        return True
    return False


assert draw_branch_lanes(of([("only", "trunk")])) == [
    "* only"
], "one entry on one lane"
assert draw_branch_lanes(
    of([("a", "trunk"), ("b", "trunk"), ("c", "trunk")])
) == ["* a", "* b", "* c"], "a history with no branching at all"
assert draw_branch_lanes(
    of(
        [
            ("a", "trunk"),
            ("b", "trunk"),
            ("c", "spur"),
            ("d", "trunk"),
            ("e", "spur"),
        ]
    )
) == [
    "* a",
    "* b",
    "| * c",
    "* | d",
    "  * e",
], "a spur beside the trunk, and the trunk's lane left empty once it ends"
assert draw_branch_lanes(
    of(
        [
            ("r1", "trunk"),
            ("r2", "side"),
            ("r3", "trunk"),
            ("r4", "side"),
            ("r5", "hot"),
            ("r6", "hot"),
        ]
    )
) == [
    "* r1",
    "| * r2",
    "* | r3",
    "  * r4",
    "* r5",
    "* r6",
], "a lane let go of is handed to the next branch to arrive"
assert draw_branch_lanes(
    of(
        [
            ("p", "one"),
            ("q", "two"),
            ("s", "three"),
            ("t", "one"),
            ("u", "two"),
            ("v", "three"),
        ]
    )
) == [
    "* p",
    "| * q",
    "| | * s",
    "* | | t",
    "  * | u",
    "    * v",
], "three lanes held at once and released from the left"
assert draw_branch_lanes(of([("x", "alpha"), ("y", "beta")])) == [
    "* x",
    "* y",
], "a branch of one entry is gone before the next branch arrives"
assert rejects([]), "an empty list is rejected"
assert rejects("nope"), "a bare string is rejected"
assert rejects([7]), "an entry that is not a mapping"
assert rejects([{"id": "a"}]), "an entry with no branch is rejected"
assert rejects([{"id": "", "branch": "trunk"}]), "an empty id is rejected"
assert rejects([{"id": "a", "branch": 5}]), "a branch that is not a string is rejected"
assert rejects(of([("a", "trunk"), ("a", "spur")])), "a repeated id is rejected"
print("ok")
