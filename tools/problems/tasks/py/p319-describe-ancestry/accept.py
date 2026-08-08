from solution import describe_ancestry

TRAIL = {
    "init": [],
    "alpha": ["init"],
    "beta": ["alpha"],
    "gamma": ["alpha"],
    "delta": ["beta", "gamma"],
    "solo": [],
}


def rejects(history, one, other):
    try:
        describe_ancestry(history, one, other)
    except ValueError:
        return True
    return False


assert describe_ancestry(TRAIL, "alpha", "alpha") == "same", "a checkpoint and itself"
assert describe_ancestry(TRAIL, "init", "beta") == "behind:2", "two steps back"
assert describe_ancestry(TRAIL, "beta", "init") == "ahead:2", "two steps forward"
assert describe_ancestry(TRAIL, "beta", "gamma") == "apart", "two strands of one fork"
assert describe_ancestry(TRAIL, "alpha", "delta") == "behind:2", "through a fold"
assert (
    describe_ancestry(TRAIL, "delta", "alpha") == "ahead:2"
), "the fold seen the other way"
assert describe_ancestry(TRAIL, "gamma", "delta") == "behind:1", "a single step back"
assert (
    describe_ancestry(TRAIL, "init", "delta") == "behind:3"
), "the shortest of two routes"
assert describe_ancestry(TRAIL, "solo", "init") == "apart", "two openings never meet"
assert describe_ancestry(TRAIL, "init", "solo") == "apart", "and neither way round"
assert rejects(TRAIL, "init", "zeta"), "an unknown checkpoint"
assert rejects({"a": ["z"]}, "a", "a"), "an unknown predecessor"
assert rejects({"a": [], "b": [7]}, "a", "b"), "a predecessor that is not a name"
assert rejects({"a": "b"}, "a", "a"), "a value that is not a list"
assert rejects([], "a", "a"), "a history that is not a mapping"
print("ok")
