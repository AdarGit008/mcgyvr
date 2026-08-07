from solution import sweep_arena_blocks


def slot(size, links, cleanup):
    return {"size": size, "links": links, "cleanup": cleanup}


def rejects(slots, anchors):
    try:
        sweep_arena_blocks(slots, anchors)
    except ValueError:
        return True
    return False


assert sweep_arena_blocks([], []) == {
    "blocks": [],
    "reclaimed": 0,
    "cleanups": [],
}, "an empty arena frees nothing"
assert sweep_arena_blocks(
    [slot(8, [], None), slot(4, [], None)], [0, 1]
) == {"blocks": [], "reclaimed": 0, "cleanups": []}, (
    "an arena held whole yields no block"
)
assert sweep_arena_blocks(
    [slot(8, [], None), slot(4, [], None), slot(2, [], None)], []
) == {"blocks": [[0, 14]], "reclaimed": 14, "cleanups": []}, (
    "with no anchor the whole arena merges into one block"
)
assert sweep_arena_blocks(
    [
        slot(8, [1], None),
        slot(4, [], None),
        slot(16, [], "close-file"),
        slot(32, [], None),
        slot(4, [0], "flush"),
    ],
    [0],
) == {
    "blocks": [[2, 52]],
    "reclaimed": 52,
    "cleanups": ["close-file", "flush"],
}, "three freed slots side by side make one block and two cleanups"
assert sweep_arena_blocks(
    [
        slot(2, [2], None),
        slot(3, [], "a"),
        slot(5, [], None),
        slot(7, [], "b"),
        slot(1, [], None),
    ],
    [0],
) == {
    "blocks": [[1, 3], [3, 8]],
    "reclaimed": 11,
    "cleanups": ["a", "b"],
}, "a marked slot between two free stretches keeps the blocks apart"
assert sweep_arena_blocks(
    [slot(4, [1], None), slot(4, [0], None), slot(9, [], "spill")], [1]
) == {"blocks": [[2, 9]], "reclaimed": 9, "cleanups": ["spill"]}, (
    "links are followed in both directions of a mutual pair"
)
assert sweep_arena_blocks([slot(6, [], "only"), slot(1, [], None)], [1]) == {
    "blocks": [[0, 6]],
    "reclaimed": 6,
    "cleanups": ["only"],
}, "a block may open at slot zero"

assert rejects("arena", []), "an arena is a list"
assert rejects([slot(1, [], None)], 0), "the anchors are a list"
assert rejects([slot(0, [], None)], []), "a size of zero is no size"
assert rejects([slot(4, [3], None)], []), "slot 3 is outside a one-slot arena"
assert rejects([slot(4, [], None)], [1]), "an anchor must name a slot"
assert rejects([slot(4, [], 7)], []), "a cleanup is a name or null"
assert rejects([slot(4, "none", None)], []), "links must be a list"
print("ok")
