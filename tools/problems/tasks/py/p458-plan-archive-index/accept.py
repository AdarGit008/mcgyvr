from solution import plan_archive_index

assert plan_archive_index([["a", 0, 4], ["b", 4, 6]], 10) == {
    "fault": "",
    "blame": [],
    "order": ["a", "b"],
    "gaps": [],
    "slack": 0,
    "used": 10,
}, "two members butted together fill the archive exactly"
assert plan_archive_index([["b", 6, 2], ["a", 1, 3]], 12) == {
    "fault": "",
    "blame": [],
    "order": ["a", "b"],
    "gaps": [[0, 1], [4, 2]],
    "slack": 4,
    "used": 5,
}, "the index is read in offset order and the holes are named"
assert plan_archive_index([], 8) == {
    "fault": "",
    "blame": [],
    "order": [],
    "gaps": [],
    "slack": 8,
    "used": 0,
}, "an index with nothing in it is all trailing room"
assert plan_archive_index([], 0) == {
    "fault": "",
    "blame": [],
    "order": [],
    "gaps": [],
    "slack": 0,
    "used": 0,
}, "an empty index over an empty archive"
assert plan_archive_index([["mark", 5, 0], ["a", 0, 10]], 10) == {
    "fault": "",
    "blame": [],
    "order": ["a", "mark"],
    "gaps": [],
    "slack": 0,
    "used": 10,
}, "a member of no length inside another is not a clash"
assert plan_archive_index([["mark", 10, 0], ["a", 0, 10]], 10) == {
    "fault": "",
    "blame": [],
    "order": ["a", "mark"],
    "gaps": [],
    "slack": 0,
    "used": 10,
}, "a member of no length may sit on the very end"
assert plan_archive_index([["a", 0, 4], ["b", 8, 5]], 10) == {
    "fault": "truncated",
    "blame": ["b"],
    "order": ["a", "b"],
    "gaps": [],
    "slack": 0,
    "used": 0,
}, "a member reaching past the end is called truncated"
assert plan_archive_index([["z", 11, 0]], 10) == {
    "fault": "truncated",
    "blame": ["z"],
    "order": ["z"],
    "gaps": [],
    "slack": 0,
    "used": 0,
}, "even a member of no length must start inside the archive"
assert plan_archive_index([["a", 0, 5], ["b", 3, 4]], 20) == {
    "fault": "overlap",
    "blame": ["a", "b"],
    "order": ["a", "b"],
    "gaps": [],
    "slack": 0,
    "used": 0,
}, "two members sharing bytes are both blamed"
assert plan_archive_index([["a", 0, 5], ["b", 5, 4]], 20) == {
    "fault": "",
    "blame": [],
    "order": ["a", "b"],
    "gaps": [],
    "slack": 11,
    "used": 9,
}, "one member ending where the next begins is no clash"
assert plan_archive_index([["big", 2, 5], ["small", 2, 1]], 20) == {
    "fault": "overlap",
    "blame": ["small", "big"],
    "order": ["small", "big"],
    "gaps": [],
    "slack": 0,
    "used": 0,
}, "at one offset the shorter member is read first"
assert plan_archive_index([["zed", 2, 0], ["ann", 2, 0]], 20) == {
    "fault": "",
    "blame": [],
    "order": ["ann", "zed"],
    "gaps": [],
    "slack": 20,
    "used": 0,
}, "members level on offset and length are read by name"
assert plan_archive_index([["a", 0, 9], ["b", 3, 20]], 10) == {
    "fault": "truncated",
    "blame": ["b"],
    "order": ["a", "b"],
    "gaps": [],
    "slack": 0,
    "used": 0,
}, "a member that both overruns and clashes is called truncated"


def rejects(entries, total):
    try:
        plan_archive_index(entries, total)
    except ValueError:
        return True
    return False


assert rejects("no", 4), "an index that is not a list is refused"
assert rejects([], -1), "a negative archive size is refused"
assert rejects([], 2.5), "a fractional archive size is refused"
assert rejects([["a", 0]], 4), "an entry that is not a triple is refused"
assert rejects([["", 0, 1]], 4), "an empty name is refused"
assert rejects([[7, 0, 1]], 4), "a name that is not a string is refused"
assert rejects([["a", 0, 1], ["a", 2, 1]], 4), "one name carried twice is refused"
assert rejects([["a", -1, 1]], 4), "a negative offset is refused"
assert rejects([["a", 0.5, 1]], 4), "a fractional offset is refused"
assert rejects([["a", 0, -1]], 4), "a negative length is refused"
assert rejects([["a", 0, 1.5]], 4), "a fractional length is refused"
print("ok")
