from solution import route_log_records

RULES = [
    {"sink": "audit", "least": "info", "tag": "billing", "stop": False},
    {"sink": "pager", "least": "error", "tag": "", "stop": True},
    {"sink": "file", "least": "trace", "tag": "", "stop": False},
    {"sink": "audit", "least": "debug", "tag": "", "stop": False},
]

SOUND = [{"sink": "a", "least": "info", "tag": "", "stop": False}]
ONE = [{"level": "info", "tag": ""}]


def rejects(rules, records, spare):
    try:
        route_log_records(rules, records, spare)
    except ValueError:
        return True
    return False


assert route_log_records(
    RULES,
    [
        {"level": "info", "tag": "billing"},
        {"level": "error", "tag": "billing"},
        {"level": "trace", "tag": "web"},
        {"level": "fatal", "tag": "web"},
        {"level": "debug", "tag": "billing"},
    ],
    "held",
) == [
    {"at": 0, "sinks": ["audit", "file"]},
    {"at": 1, "sinks": ["audit", "pager"]},
    {"at": 2, "sinks": ["file"]},
    {"at": 3, "sinks": ["pager"]},
    {"at": 4, "sinks": ["file", "audit"]},
], "the whole rule list against five records at once"

assert route_log_records([], ONE, "held") == [
    {"at": 0, "sinks": ["held"]}
], "with no rules at all everything falls to the spare"

assert route_log_records(
    [{"sink": "x", "least": "error", "tag": "", "stop": False}], ONE, "held"
) == [{"at": 0, "sinks": ["held"]}], "a record below every floor falls to the spare"

assert route_log_records(
    [
        {"sink": "a", "least": "trace", "tag": "", "stop": False},
        {"sink": "a", "least": "trace", "tag": "", "stop": False},
    ],
    ONE,
    "held",
) == [{"at": 0, "sinks": ["a"]}], "one sink named by two rules is added once"

assert route_log_records(
    [
        {"sink": "a", "least": "trace", "tag": "", "stop": True},
        {"sink": "b", "least": "trace", "tag": "", "stop": False},
    ],
    ONE,
    "held",
) == [{"at": 0, "sinks": ["a"]}], "a stopping rule shuts out the rules behind it"

assert route_log_records(
    [{"sink": "a", "least": "trace", "tag": "web", "stop": False}],
    [
        {"level": "fatal", "tag": "web"},
        {"level": "fatal", "tag": "webs"},
        {"level": "fatal", "tag": ""},
    ],
    "held",
) == [
    {"at": 0, "sinks": ["a"]},
    {"at": 1, "sinks": ["held"]},
    {"at": 2, "sinks": ["held"]},
], "a rule's tag must be the record's tag exactly"

assert route_log_records(
    [{"sink": "a", "least": "warn", "tag": "", "stop": False}],
    [
        {"level": "info", "tag": ""},
        {"level": "warn", "tag": ""},
        {"level": "error", "tag": ""},
    ],
    "held",
) == [
    {"at": 0, "sinks": ["held"]},
    {"at": 1, "sinks": ["a"]},
    {"at": 2, "sinks": ["a"]},
], "the floor takes in the level it names"

assert route_log_records(RULES, [], "held") == [], "no records make no rows"

assert rejects("rules", ONE, "held"), "rules that are not a list are rejected"
assert rejects(SOUND, "records", "held"), "records that are not a list are rejected"
assert rejects([["a"]], ONE, "held"), "a rule that is not a mapping is rejected"
assert rejects(
    [{"sink": "", "least": "info", "tag": "", "stop": False}], ONE, "held"
), "an empty sink name is rejected"
assert rejects(
    [{"sink": "a", "least": "loud", "tag": "", "stop": False}], ONE, "held"
), "a rule naming no known level is rejected"
assert rejects(
    [{"sink": "a", "least": "info", "tag": 5, "stop": False}], ONE, "held"
), "a tag that is not a string is rejected"
assert rejects(
    [{"sink": "a", "least": "info", "tag": "", "stop": "yes"}], ONE, "held"
), "a stop that is not a boolean is rejected"
assert rejects(SOUND, [["info"]], "held"), "a record that is not a mapping is rejected"
assert rejects(
    SOUND, [{"level": "loud", "tag": ""}], "held"
), "a record naming no known level is rejected"
assert rejects(
    SOUND, [{"level": "info", "tag": 9}], "held"
), "a record tag that is not a string is rejected"
assert rejects(SOUND, ONE, ""), "an empty spare name is rejected"
assert rejects(SOUND, ONE, 3), "a spare name that is not a string is rejected"

print("ok")
