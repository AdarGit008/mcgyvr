from solution import walk_skip_form

FORM = [
    {"code": "q1", "options": ["yes", "no"], "jumps": [{"on": "no", "to": "close"}]},
    {"code": "q2", "options": ["car", "bus", "walk"], "jumps": [{"on": "walk", "to": "q4"}]},
    {"code": "q3", "options": ["a", "b"], "jumps": []},
    {"code": "q4", "options": ["ok", "bad"], "jumps": [{"on": "bad", "to": "close"}]},
    {"code": "q5", "options": ["1", "2"], "jumps": []},
]

assert walk_skip_form(FORM, {"q1": "yes", "q2": "walk", "q4": "ok", "q5": "2"}) == {
    "asked": ["q1", "q2", "q4", "q5"],
    "blank": [],
    "wrong": [],
    "stray": [],
    "ending": "spent",
}, "a jump forward skips the step it steps over"
assert walk_skip_form(FORM, {"q1": "no", "q3": "a"}) == {
    "asked": ["q1"],
    "blank": [],
    "wrong": [],
    "stray": ["q3"],
    "ending": "close",
}, "closing at once leaves an answer to an unreached step stray"
assert walk_skip_form(FORM, {"q1": "maybe", "q2": "bus", "q3": "b", "q4": "bad"}) == {
    "asked": ["q1", "q2", "q3", "q4"],
    "blank": [],
    "wrong": ["q1"],
    "stray": [],
    "ending": "close",
}, "an answer off the option list falls through rather than jumping"
assert walk_skip_form(FORM, {"q2": "car"}) == {
    "asked": ["q1", "q2", "q3", "q4", "q5"],
    "blank": ["q1", "q3", "q4", "q5"],
    "wrong": [],
    "stray": [],
    "ending": "spent",
}, "an unheard step falls through to the next step"
assert walk_skip_form(FORM, {}) == {
    "asked": ["q1", "q2", "q3", "q4", "q5"],
    "blank": ["q1", "q2", "q3", "q4", "q5"],
    "wrong": [],
    "stray": [],
    "ending": "spent",
}, "an empty answer set still walks the whole form"
assert walk_skip_form(
    FORM, {"q1": "yes", "q2": "walk", "q3": "a", "q4": "bad", "q5": "1"}
) == {
    "asked": ["q1", "q2", "q4"],
    "blank": [],
    "wrong": [],
    "stray": ["q3", "q5"],
    "ending": "close",
}, "stray codes come out in the order the form declares them"
assert walk_skip_form([{"code": "only", "options": ["go"], "jumps": []}], {"only": "go"}) == {
    "asked": ["only"],
    "blank": [],
    "wrong": [],
    "stray": [],
    "ending": "spent",
}, "a one-step form runs off the end"


def rejects(steps, replies):
    try:
        walk_skip_form(steps, replies)
    except ValueError:
        return True
    return False


assert rejects([], {}), "an empty form is refused"
assert rejects(["q1"], {}), "a step must be a mapping"
assert rejects(
    [{"code": "a", "options": ["x"], "jumps": []}, {"code": "a", "options": ["y"], "jumps": []}], {}
), "two steps may not share a code"
assert rejects([{"code": "a", "options": [], "jumps": []}], {}), "a step needs an option"
assert rejects(
    [{"code": "a", "options": ["x"], "jumps": [{"on": "z", "to": "close"}]}], {}
), "a jump may not fire on a foreign option"
assert rejects(
    [{"code": "a", "options": ["x"], "jumps": [{"on": "x", "to": "a"}]}], {}
), "a jump may not point at its own step"
assert rejects(
    [
        {"code": "a", "options": ["x"], "jumps": [{"on": "x", "to": "close"}, {"on": "x", "to": "b"}]},
        {"code": "b", "options": ["y"], "jumps": []},
    ],
    {},
), "two jumps of one step may not fire on the same option"
assert rejects(FORM, {"nowhere": "yes"}), "an answer to an undeclared step is refused"
assert rejects(FORM, {"q1": 3}), "an answer must be a string"
print("ok")
