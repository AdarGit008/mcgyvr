from solution import choose_upgrades


def req(installed, offers, rules):
    return {"installed": installed, "offers": offers, "rules": rules}


def rule(name, low, high):
    return {"package": name, "min": low, "max": high}


def move(name, to, action):
    return {"package": name, "to": to, "action": action}


def snag(name, why):
    return {"package": name, "why": why}


def rejects(value):
    try:
        choose_upgrades(value)
    except ValueError:
        return True
    return False


assert choose_upgrades(
    req({"a": "1.4"}, {"a": ["1.4", "1.6", "2.0"]}, [rule("a", "1.0", "1.9")])
) == {
    "moves": [move("a", "1.4", "hold")],
    "snags": [],
}, "a permitted release running today stays put"
assert choose_upgrades(
    req({"a": "1.4"}, {"a": ["1.4", "1.6", "2.0"]}, [rule("a", "1.5", "2.5")])
) == {
    "moves": [move("a", "1.6", "lift")],
    "snags": [],
}, "a lift takes the lowest permitted release above today"
assert choose_upgrades(req({}, {"b": ["2.0", "2.4"]}, [rule("b", "2.0", "3.0")])) == {
    "moves": [move("b", "2.0", "fetch")],
    "snags": [],
}, "a library running nothing takes the lowest permitted release"
assert choose_upgrades(
    req({"c": "5.0"}, {"c": ["1.0", "2.0", "5.0"]}, [rule("c", "1.0", "2.0")])
) == {
    "moves": [],
    "snags": [snag("c", "drop")],
}, "permitted releases all below today are a drop"
assert choose_upgrades(
    req({"d": "1.0"}, {"d": ["1.0"]}, [rule("d", "3.0", "4.0")])
) == {
    "moves": [],
    "snags": [snag("d", "none")],
}, "no permitted release at all is none"
assert choose_upgrades(
    req(
        {"e": "1.0"},
        {"e": ["1.0", "1.5", "2.0"]},
        [rule("e", "1.0", "2.0"), rule("e", "1.5", "3.0")],
    )
) == {
    "moves": [move("e", "1.5", "lift")],
    "snags": [],
}, "every rule on a library must be cleared"
assert choose_upgrades(
    req({"f": "9.0"}, {"f": ["9.0", "10.0"]}, [rule("f", "9.0", "10.0")])
) == {
    "moves": [move("f", "9.0", "hold")],
    "snags": [],
}, "the first group orders as a number"
assert choose_upgrades(req({}, {"g": ["1.2", "1.10"]}, [rule("g", "1.0", "1.20")])) == {
    "moves": [move("g", "1.2", "fetch")],
    "snags": [],
}, "the second group orders as a number too"
assert choose_upgrades(
    req(
        {"h": "1.0", "z": "9.9"},
        {"h": ["1.0", "1.1"], "z": ["9.9"]},
        [rule("h", "1.0", "1.5")],
    )
) == {
    "moves": [move("h", "1.0", "hold")],
    "snags": [],
}, "an unruled library is reported nowhere"
assert choose_upgrades(
    req(
        {},
        {"b": ["1.0"], "a": ["1.0"], "y": ["1.0"], "x": ["5.0"]},
        [
            rule("b", "1.0", "2.0"),
            rule("y", "9.0", "9.9"),
            rule("a", "1.0", "2.0"),
            rule("x", "9.0", "9.9"),
        ],
    )
) == {
    "moves": [move("a", "1.0", "fetch"), move("b", "1.0", "fetch")],
    "snags": [snag("x", "none"), snag("y", "none")],
}, "both reports run in ascending library order"
assert choose_upgrades(req({"a": "1.0"}, {"a": ["1.0"]}, [])) == {
    "moves": [],
    "snags": [],
}, "no rules, nothing to report"

assert rejects([1, 2]), "a request that is not a mapping is rejected"
assert rejects({"installed": [], "offers": {}, "rules": []}), "installed must be a mapping"
assert rejects({"installed": {}, "offers": [], "rules": []}), "offers must be a mapping"
assert rejects({"installed": {}, "offers": {}, "rules": {}}), "rules must be a list"
assert rejects(req({}, {"a": ["1.0"]}, ["a"])), "a rule that is not a mapping"
assert rejects(
    req({}, {"a": ["1.0"]}, [rule("q", "1.0", "2.0")])
), "a rule on an uncarried library is rejected"
assert rejects(
    req({}, {"a": ["1.0"]}, [rule("a", "2.0", "1.0")])
), "a min above its max is rejected"
assert rejects(req({"q": "1.0"}, {"a": ["1.0"]}, [])), "an uncarried running library"
assert rejects(req({}, {"a": []}, [])), "an empty offers entry is rejected"
assert rejects(req({}, {"a": ["1.0", "1.0"]}, [])), "a repeated release is rejected"
assert rejects(req({}, {"a": ["1"]}, [])), "a release of one group is rejected"
assert rejects(req({}, {"a": ["1.0.0"]}, [])), "a release of three groups is rejected"
assert rejects(req({}, {"a": ["01.2"]}, [])), "a leading zero is rejected"

print("ok")
