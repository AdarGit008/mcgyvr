from solution import hold_shelf_replay

assert hold_shelf_replay(
    [
        "join ana",
        "join bob",
        "join ana",
        "serve",
        "serve",
        "serve",
        "leave bob",
        "join cal",
        "leave bob",
        "join bob",
        "serve",
    ]
) == [
    "at:1",
    "at:2",
    "no:again",
    "take:ana",
    "take:bob",
    "idle",
    "no:absent",
    "at:1",
    "no:absent",
    "at:2",
    "take:cal",
], "join, duplicate join, serving down to empty, rejoining"
assert hold_shelf_replay(
    ["join a", "join b", "join c", "leave b", "join d", "serve", "serve"]
) == [
    "at:1",
    "at:2",
    "at:3",
    "out",
    "at:3",
    "take:a",
    "take:c",
], "leaving from the middle closes the gap"
assert hold_shelf_replay([]) == [], "no slips, no answers"
assert hold_shelf_replay(["serve"]) == ["idle"], "serving an empty queue"


def rejects(value):
    try:
        hold_shelf_replay(value)
    except ValueError:
        return True
    return False


assert rejects(["dance ana"]), "unknown verb throws"
assert rejects(["join "]), "empty name throws"
assert rejects(["leave"]), "nameless leave throws"
assert rejects(["serve now"]), "serve with a payload throws"
assert rejects([42]), "non-string slip throws"
print("ok")
