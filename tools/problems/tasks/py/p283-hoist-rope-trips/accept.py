from solution import plan_hoist_trips

assert plan_hoist_trips(
    [{"tag": "north", "level": 0}, {"tag": "south", "level": 6}], [3, 3, 0]
) == ["south", "south", "north"], "descending is the cheap direction"
assert plan_hoist_trips(
    [{"tag": "a", "level": 0}, {"tag": "b", "level": 10}], [5]
) == ["b"], "a five-level drop beats a five-level climb"
assert plan_hoist_trips(
    [{"tag": "west", "level": 4}, {"tag": "east", "level": 4}], [4]
) == ["east"], "an equal cost falls to the earlier tag, not the earlier position"
assert plan_hoist_trips([{"tag": "solo", "level": 0}], [6, 1]) == [
    "solo",
    "idle",
], "reaching twelve rope retires the hoist"
assert plan_hoist_trips([{"tag": "solo", "level": 0}], [5, 4, 3]) == [
    "solo",
    "solo",
    "solo",
], "eleven rope leaves a hoist in service"
assert plan_hoist_trips(
    [{"tag": "a", "level": 0}, {"tag": "b", "level": 10}], [5, 5, 0, 10, 10, 10]
) == ["b", "b", "a", "b", "a", "idle"], "the bank wears out one hoist at a time"
assert plan_hoist_trips([{"tag": "solo", "level": 2}], []) == [], "no stops"


def rejects(hoists, stops):
    try:
        plan_hoist_trips(hoists, stops)
    except ValueError:
        return True
    return False


assert rejects([], [1]), "empty bank"
assert rejects([{"tag": "a", "level": 0}, {"tag": "a", "level": 1}], [1]), (
    "repeated tag"
)
assert rejects([{"tag": "idle", "level": 0}], [1]), "the word idle cannot be a tag"
assert rejects([{"tag": "", "level": 0}], [1]), "an empty tag"
assert rejects([{"tag": "a", "level": -1}], [1]), "a level below the ground"
assert rejects([{"tag": "a", "level": 0}], [1.5]), "a fractional stop"
assert rejects([{"tag": "a", "level": 0}], "3"), "stops is not a list"
print("ok")
