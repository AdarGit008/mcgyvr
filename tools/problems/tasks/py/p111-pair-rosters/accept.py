from solution import pair_rosters

assert pair_rosters(
    [{"tag": "t1", "role": "lead"}],
    [{"tag": "t1", "room": 12}, {"tag": "t2", "room": 9}],
    "tag",
) == [
    {"tag": "t1", "role": "lead", "room": 12}
], "a partner at position 0 of the second roster must not be dropped"
assert pair_rosters(
    [{"tag": "t2", "role": "scout"}, {"tag": "t9", "role": "cook"}, {"tag": "t1"}],
    [{"tag": "t1", "room": 12}, {"tag": "t2", "room": 9}],
    "tag",
) == [
    {"tag": "t2", "role": "scout", "room": 9},
    {"tag": "t1", "room": 12},
], "unmatched records drop, the rest keep first-roster order"
assert pair_rosters(
    [{"tag": "t1", "role": "a"}, {"tag": "t1", "role": "b"}],
    [{"tag": "t1", "room": 3}],
    "tag",
) == [
    {"tag": "t1", "role": "a", "room": 3},
    {"tag": "t1", "role": "b", "room": 3},
], "repeated first-roster keys each join"
assert pair_rosters([], [{"tag": "t1"}], "tag") == [], "an empty first roster"
assert (
    pair_rosters([{"tag": "t3"}], [{"tag": "t1", "room": 1}], "tag") == []
), "no partners at all"


def rejects(left, right, key):
    try:
        pair_rosters(left, right, key)
    except ValueError:
        return True
    return False


assert rejects(
    [{"tag": "t1"}], [{"tag": "t1", "room": 1}, {"tag": "t1", "room": 2}], "tag"
), "a repeated key in the second roster is an error"
assert rejects(
    [{"role": "lead"}], [{"tag": "t1"}], "tag"
), "a missing key column is an error"
assert rejects([{"tag": 4}], [{"tag": "t1"}], "tag"), "a non-string key value is an error"
print("ok")
