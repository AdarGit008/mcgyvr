from solution import decide_switch

ramping = {"mode": "ramp", "barred": ["dee"], "waved": ["ann"], "cutoff": 30}

assert decide_switch(ramping, {"id": "dee", "slot": 0}) == {
    "open": "no",
    "why": "barred",
}, "the barred list is read before anything else"
assert decide_switch(ramping, {"id": "ann", "slot": 99}) == {
    "open": "yes",
    "why": "waved",
}, "a waved caller ignores the ramp entirely"
assert decide_switch(ramping, {"id": "bob", "slot": 29}) == {
    "open": "yes",
    "why": "ramp",
}, "the last slot below the cutoff is let through"
assert decide_switch(ramping, {"id": "bob", "slot": 30}) == {
    "open": "no",
    "why": "held",
}, "a slot equal to the cutoff is held back"
assert decide_switch(
    {"mode": "ramp", "barred": [], "waved": [], "cutoff": 0}, {"id": "bob", "slot": 0}
) == {"open": "no", "why": "held"}, "a cutoff of zero lets nobody onto the ramp"
assert decide_switch(
    {"mode": "ramp", "barred": [], "waved": [], "cutoff": 100}, {"id": "bob", "slot": 99}
) == {"open": "yes", "why": "ramp"}, "a cutoff of a hundred takes the highest slot"

dark = {"mode": "dark", "barred": ["dee"], "waved": ["ann"], "cutoff": 100}
assert decide_switch(dark, {"id": "ann", "slot": 0}) == {
    "open": "no",
    "why": "dark",
}, "dark outranks the waved list"
assert decide_switch(dark, {"id": "dee", "slot": 0}) == {
    "open": "no",
    "why": "barred",
}, "barred still outranks dark"

live = {"mode": "live", "barred": ["dee"], "waved": ["ann"], "cutoff": 0}
assert decide_switch(live, {"id": "bob", "slot": 99}) == {
    "open": "yes",
    "why": "live",
}, "live ignores the cutoff"
assert decide_switch(live, {"id": "ann", "slot": 99}) == {
    "open": "yes",
    "why": "waved",
}, "the waved list is read before the mode"
assert decide_switch(live, {"id": "dee", "slot": 0}) == {
    "open": "no",
    "why": "barred",
}, "barred outranks live too"


def rejects(one, two):
    try:
        decide_switch(one, two)
    except ValueError:
        return True
    return False


assert rejects(
    {"mode": "off", "barred": [], "waved": [], "cutoff": 0}, {"id": "bob", "slot": 0}
), "an unknown mode is rejected"
assert rejects(
    {"mode": "ramp", "barred": [], "waved": [], "cutoff": 101}, {"id": "bob", "slot": 0}
), "a cutoff past a hundred is rejected"
assert rejects(
    {"mode": "ramp", "barred": [], "waved": [], "cutoff": -1}, {"id": "bob", "slot": 0}
), "a negative cutoff is rejected"
assert rejects(
    {"mode": "ramp", "barred": "dee", "waved": [], "cutoff": 0}, {"id": "bob", "slot": 0}
), "a barred list that is a string is rejected"
assert rejects(
    {"mode": "ramp", "barred": ["dee", "dee"], "waved": [], "cutoff": 0},
    {"id": "bob", "slot": 0},
), "one id named twice in a list is rejected"
assert rejects(
    {"mode": "ramp", "barred": ["ann"], "waved": ["ann"], "cutoff": 0},
    {"id": "bob", "slot": 0},
), "an id both barred and waved is rejected"
assert rejects(
    {"mode": "ramp", "barred": [], "cutoff": 0}, {"id": "bob", "slot": 0}
), "a setting without waved is rejected"
assert rejects(ramping, {"id": "bob", "slot": 100}), "a slot of a hundred is rejected"
assert rejects(ramping, {"id": "", "slot": 0}), "an empty id is rejected"
assert rejects(ramping, {"id": "bob"}), "a caller without a slot is rejected"
print("ok")
