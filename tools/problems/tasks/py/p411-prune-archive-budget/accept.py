from solution import prune_archive_budget

vault = [
    {"label": "A", "size": 500, "age": 10},
    {"label": "B", "size": 300, "age": 40},
    {"label": "C", "size": 200, "age": 5},
    {"label": "D", "size": 100, "age": 40},
]

assert prune_archive_budget(vault, 600, 30, 1) == {
    "removed": ["B", "D", "A"],
    "held": 200,
    "over": 0,
    "stale": 0,
}, "age clears two, then the budget claims a third"

assert prune_archive_budget(vault, 100, 30, 2) == {
    "removed": ["B", "D"],
    "held": 700,
    "over": 600,
    "stale": 0,
}, "the least number halts the thinning and the excess is reported"

assert prune_archive_budget(vault, 5000, 100, 0) == {
    "removed": [],
    "held": 1100,
    "over": 0,
    "stale": 0,
}, "nothing old and nothing over budget leaves the archive alone"

assert prune_archive_budget(
    [{"label": "P", "size": 10, "age": 99}, {"label": "Q", "size": 10, "age": 99}], 1000, 5, 1
) == {
    "removed": ["P"],
    "held": 10,
    "over": 0,
    "stale": 1,
}, "an exact tie goes to the earlier label, and a stale survivor is counted"

assert prune_archive_budget(
    [{"label": "A", "size": 10, "age": 9}, {"label": "B", "size": 20, "age": 9}], 1000, 5, 0
) == {
    "removed": ["B", "A"],
    "held": 0,
    "over": 0,
    "stale": 0,
}, "equally old files go biggest first, and the archive may empty"

assert prune_archive_budget([], 100, 5, 0) == {
    "removed": [],
    "held": 0,
    "over": 0,
    "stale": 0,
}, "an empty archive"

assert prune_archive_budget([{"label": "S", "size": 900, "age": 1}], 100, 5, 1) == {
    "removed": [],
    "held": 900,
    "over": 800,
    "stale": 0,
}, "a lone file may not be removed but is still over"


def rejects(files, budget, limit, least):
    try:
        prune_archive_budget(files, budget, limit, least)
    except ValueError:
        return True
    return False


assert rejects("x", 100, 5, 0), "an archive that is not a list"
assert rejects([4], 100, 5, 0), "a file that is not a record"
assert rejects([{"label": "", "size": 1, "age": 1}], 100, 5, 0), "an empty label"
assert rejects(
    [{"label": "A", "size": 1, "age": 1}, {"label": "A", "size": 2, "age": 2}], 100, 5, 0
), "one label twice"
assert rejects([{"label": "A", "size": -1, "age": 1}], 100, 5, 0), "a negative size"
assert rejects([{"label": "A", "size": 1, "age": 1.5}], 100, 5, 0), "a fractional age"
assert rejects(vault, -1, 5, 0), "a negative budget"
assert rejects(vault, 100, 0, 0), "an age limit of nothing"
assert rejects(vault, 100, 5, -1), "a negative least number"
assert rejects(vault, 100, 5, 1.5), "a fractional least number"
print("ok")
