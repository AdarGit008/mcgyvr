from solution import stack_address_panel

PARTS = {
    "name": "Dela Voss",
    "unit": "  Flat 3 ",
    "road": "Ember Lane",
    "city": "brack",
    "pin": "tt-90",
    "care": "   ",
}

PLAN = [
    {"slots": ["name"], "fold": "keep", "must": True},
    {"slots": ["care"], "fold": "keep", "must": False},
    {"slots": ["unit", "road"], "fold": "keep", "must": True},
    {"slots": ["city"], "fold": "up", "must": True},
    {"slots": ["pin"], "fold": "up", "must": True},
]

assert stack_address_panel(PARTS, PLAN) == [
    "Dela Voss",
    "Flat 3 Ember Lane",
    "BRACK",
    "TT-90",
], "a step with nothing to write and must false is dropped"

assert stack_address_panel(
    PARTS, [{"slots": ["care", "road"], "fold": "down", "must": True}]
) == ["ember lane"], "a blank slot is passed over and the rest still writes the line"

assert stack_address_panel(
    PARTS, [{"slots": ["unit"], "fold": "keep", "must": True}]
) == ["Flat 3"], "outer blanks go and inner ones stay"

assert stack_address_panel(
    PARTS,
    [
        {"slots": ["name", "pin"], "fold": "up", "must": True},
        {"slots": ["name", "pin"], "fold": "down", "must": True},
    ],
) == ["DELA VOSS TT-90", "dela voss tt-90"], "up and down fold the whole joined line"

assert stack_address_panel(
    {"road": 41, "city": "Ort"},
    [
        {"slots": ["road"], "fold": "keep", "must": False},
        {"slots": ["city"], "fold": "keep", "must": True},
    ],
) == ["Ort"], "a slot holding something other than text is passed over"

assert (
    stack_address_panel(
        PARTS, [{"slots": ["gone", "care"], "fold": "keep", "must": False}]
    )
    == []
), "a panel may end up with no lines at all"


def rejects(parts, plan):
    try:
        stack_address_panel(parts, plan)
    except ValueError:
        return True
    return False


assert rejects(
    PARTS, [{"slots": ["care"], "fold": "keep", "must": True}]
), "a must step that finds nothing is fatal"
assert rejects("bag", PLAN), "parts must be a record"
assert rejects(PARTS, []), "an empty plan is rejected"
assert rejects(PARTS, "plan"), "plan must be a list"
assert rejects(PARTS, ["name"]), "a step must be a record"
assert rejects(
    PARTS, [{"slots": [], "fold": "keep", "must": True}]
), "a step naming no slot is rejected"
assert rejects(
    PARTS, [{"slots": ["name", ""], "fold": "keep", "must": True}]
), "an empty slot name is rejected"
assert rejects(
    PARTS, [{"slots": ["name"], "fold": "sideways", "must": True}]
), "an unknown fold is rejected"
assert rejects(
    PARTS, [{"slots": ["name"], "fold": "keep", "must": "yes"}]
), "must must be a boolean"
print("ok")
