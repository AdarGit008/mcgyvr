from solution import sift_event_streams

LANES = [
    {"name": "quiet", "prefix": "app.", "upTo": "notice", "last": False},
    {"name": "watch", "prefix": "", "upTo": "alarm", "last": False},
    {"name": "quiet", "prefix": "db.", "upTo": "notice", "last": False},
    {"name": "sink", "prefix": "app.", "upTo": "panic", "last": True},
]

SOUND = [{"name": "a", "prefix": "", "upTo": "panic", "last": False}]
ONE = [{"channel": "x", "severity": "chatter"}]


def rejects(lanes, events):
    try:
        sift_event_streams(lanes, events)
    except ValueError:
        return True
    return False


assert sift_event_streams(
    LANES,
    [
        {"channel": "app.web", "severity": "chatter"},
        {"channel": "db.main", "severity": "notice"},
        {"channel": "app.web", "severity": "panic"},
        {"channel": "other", "severity": "panic"},
        {"channel": "app.api", "severity": "alarm"},
    ],
) == {
    "lanes": [
        {"name": "quiet", "took": [0, 1]},
        {"name": "watch", "took": [0, 1, 4]},
        {"name": "sink", "took": [0, 2, 4]},
    ],
    "dropped": [3],
}, "four lanes over five events, names folded and one event dropped"

assert sift_event_streams(
    [
        {"name": "a", "prefix": "", "upTo": "panic", "last": False},
        {"name": "a", "prefix": "", "upTo": "panic", "last": False},
    ],
    ONE,
) == {
    "lanes": [{"name": "a", "took": [0]}],
    "dropped": [],
}, "two lanes of one name take the event once between them"

assert sift_event_streams(
    [
        {"name": "a", "prefix": "", "upTo": "panic", "last": True},
        {"name": "b", "prefix": "", "upTo": "panic", "last": False},
    ],
    ONE,
) == {
    "lanes": [{"name": "a", "took": [0]}, {"name": "b", "took": []}],
    "dropped": [],
}, "a final lane leaves the one behind it empty"

assert sift_event_streams(
    [{"name": "a", "prefix": "", "upTo": "notice", "last": False}],
    [
        {"channel": "x", "severity": "chatter"},
        {"channel": "x", "severity": "notice"},
        {"channel": "x", "severity": "alarm"},
    ],
) == {
    "lanes": [{"name": "a", "took": [0, 1]}],
    "dropped": [2],
}, "the ceiling takes in the severity it names and nothing above it"

assert sift_event_streams(
    [{"name": "a", "prefix": "app.", "upTo": "panic", "last": False}],
    [
        {"channel": "app", "severity": "panic"},
        {"channel": "app.", "severity": "panic"},
        {"channel": "application", "severity": "panic"},
    ],
) == {
    "lanes": [{"name": "a", "took": [1]}],
    "dropped": [0, 2],
}, "a prefix is matched at the opening of the channel, letter for letter"

assert sift_event_streams([], ONE) == {
    "lanes": [],
    "dropped": [0],
}, "with no lanes every event is dropped"

assert sift_event_streams(LANES, []) == {
    "lanes": [
        {"name": "quiet", "took": []},
        {"name": "watch", "took": []},
        {"name": "sink", "took": []},
    ],
    "dropped": [],
}, "with no events the lanes are still named, all empty"

assert rejects("lanes", ONE), "lanes that are not a list are rejected"
assert rejects(SOUND, "events"), "events that are not a list are rejected"
assert rejects([["a"]], ONE), "a lane that is not a mapping is rejected"
assert rejects(
    [{"name": "", "prefix": "", "upTo": "panic", "last": False}], ONE
), "an empty lane name is rejected"
assert rejects(
    [{"name": "a", "prefix": 4, "upTo": "panic", "last": False}], ONE
), "a prefix that is not a string is rejected"
assert rejects(
    [{"name": "a", "prefix": "", "upTo": "loud", "last": False}], ONE
), "a lane naming no known severity is rejected"
assert rejects(
    [{"name": "a", "prefix": "", "upTo": "panic", "last": "yes"}], ONE
), "a last that is not a boolean is rejected"
assert rejects(SOUND, [["x"]]), "an event that is not a mapping is rejected"
assert rejects(SOUND, [{"channel": "", "severity": "panic"}]), "an empty channel is rejected"
assert rejects(
    SOUND, [{"channel": "x", "severity": "loud"}]
), "an event naming no known severity is rejected"
assert rejects(
    SOUND, [{"channel": 7, "severity": "panic"}]
), "a channel that is not a string is rejected"

print("ok")
