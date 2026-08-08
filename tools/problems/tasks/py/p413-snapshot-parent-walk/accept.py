from solution import order_snapshot_load

shelf = [
    {"name": "jan", "parent": ""},
    {"name": "feb", "parent": "jan"},
    {"name": "mar", "parent": "feb"},
    {"name": "side", "parent": "jan"},
]

assert order_snapshot_load(shelf, "mar") == {
    "found": "yes",
    "order": ["jan", "feb", "mar"],
    "why": "",
}, "the whole image comes first and the wanted snapshot last"
assert order_snapshot_load(shelf, "jan") == {
    "found": "yes",
    "order": ["jan"],
    "why": "",
}, "a whole image needs nothing else"
assert order_snapshot_load(shelf, "side") == {
    "found": "yes",
    "order": ["jan", "side"],
    "why": "",
}, "a branch off the whole image loads in two steps"
assert order_snapshot_load(shelf, "nope") == {
    "found": "no",
    "order": [],
    "why": "unknown",
}, "a wanted name the archive lacks is unknown"
assert order_snapshot_load([{"name": "apr", "parent": "gone"}], "apr") == {
    "found": "no",
    "order": [],
    "why": "unknown",
}, "a parent the archive lacks is unknown, not a shorter chain"
assert order_snapshot_load(
    [{"name": "one", "parent": "two"}, {"name": "two", "parent": "one"}], "one"
) == {
    "found": "no",
    "order": [],
    "why": "cycle",
}, "two snapshots pointing at each other are a cycle"
assert order_snapshot_load([{"name": "loop", "parent": "loop"}], "loop") == {
    "found": "no",
    "order": [],
    "why": "cycle",
}, "a snapshot naming itself is a cycle"
assert order_snapshot_load([], "mar") == {
    "found": "no",
    "order": [],
    "why": "unknown",
}, "an empty archive holds nothing wanted"


def rejects(one, two):
    try:
        order_snapshot_load(one, two)
    except ValueError:
        return True
    return False


assert rejects("mar", "mar"), "an archive that is a string is rejected"
assert rejects([{"name": "jan"}], "jan"), "a snapshot without parent is rejected"
assert rejects([{"name": "", "parent": ""}], "jan"), "an empty name is rejected"
assert rejects([{"name": "jan", "parent": 3}], "jan"), (
    "a parent that is a number is rejected"
)
assert rejects(
    [{"name": "jan", "parent": ""}, {"name": "jan", "parent": "feb"}], "jan"
), "a repeated name is rejected"
assert rejects(shelf, ""), "an empty wanted name is rejected"
assert rejects(shelf, 7), "a wanted name that is a number is rejected"
print("ok")
