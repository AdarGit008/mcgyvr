from solution import read_crossing_states

plaza = [
    {"name": "quay", "start": 0, "walk": 6, "clear": 3},
    {"name": "mall", "start": 10, "walk": 5, "clear": 2},
    {"name": "pier", "start": 17, "walk": 4, "clear": 1},
]
wrap = [{"name": "lane", "start": 18, "walk": 4, "clear": 0}]

assert read_crossing_states(20, plaza, []) == [], "no moments asked about"
assert read_crossing_states(20, plaza, [0]) == ["WSW"], "a crossing offset late is already walking at second zero"
assert read_crossing_states(20, plaza, [1]) == ["WSC"], "the offset crossing has slipped into its clearing stretch"
assert read_crossing_states(20, plaza, [5, 6, 8, 9]) == ["WSS", "CSS", "CSS", "SSS"], (
    "the first crossing walks, clears and stops"
)
assert read_crossing_states(20, plaza, [10, 14, 16]) == ["SWS", "SWS", "SCS"], "the middle crossing takes its turn"
assert read_crossing_states(20, plaza, [17, 19]) == ["SSW", "SSW"], "the late crossing opens near the end of the period"
assert read_crossing_states(20, plaza, [20, 21]) == ["WSW", "WSC"], "a second period repeats the first"
assert read_crossing_states(20, plaza, [1000000]) == ["WSW"], "a far off moment folds back the same way"
assert read_crossing_states(20, wrap, [17, 18, 19, 0, 1, 2]) == ["S", "W", "W", "W", "W", "S"], (
    "a stretch that runs off the end and resumes at zero"
)
assert read_crossing_states(1, [{"name": "solo", "start": 0, "walk": 1, "clear": 0}], [0, 1, 7]) == ["W", "W", "W"], (
    "a one second period always walks"
)


def rejects(period, crossings, moments):
    try:
        read_crossing_states(period, crossings, moments)
    except ValueError:
        return True
    return False


assert rejects(0, plaza, [0]), "a period of zero"
assert rejects(86401, plaza, [0]), "a period past the ceiling"
assert rejects(1.5, plaza, [0]), "a fractional period"
assert rejects(20, [], [0]), "an empty crossing list"
assert rejects(20, "plaza", [0]), "crossings given as text"
assert rejects(20, [{"name": "a", "start": 0, "walk": 3}], [0]), "a crossing missing clear"
assert rejects(20, [{"name": "", "start": 0, "walk": 3, "clear": 1}], [0]), "an empty crossing name"
assert rejects(20, [{"name": "a", "start": 20, "walk": 3, "clear": 1}], [0]), "a start equal to the period"
assert rejects(20, [{"name": "a", "start": 0, "walk": 0, "clear": 1}], [0]), "a crossing that never walks"
assert rejects(20, [{"name": "a", "start": 0, "walk": 18, "clear": 5}], [0]), "walk plus clear outrunning the period"
assert rejects(
    20,
    [{"name": "a", "start": 0, "walk": 3, "clear": 1}, {"name": "a", "start": 5, "walk": 2, "clear": 0}],
    [0],
), "a repeated crossing name"
assert rejects(20, plaza, "0"), "moments given as text"
assert rejects(20, plaza, [-1]), "a moment below zero"
assert rejects(20, plaza, [1000001]), "a moment past the ceiling"
assert rejects(20, plaza, [2.5]), "a fractional moment"
print("ok")
