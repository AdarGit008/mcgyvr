from solution import check_load_manifest

PLAN = {
    "zones": [
        {"zone": "fore", "cap": 100, "arm": -2},
        {"zone": "mid", "cap": 200, "arm": 0},
        {"zone": "aft", "cap": 120, "arm": 4},
    ],
    "gross": 300,
    "low": -150,
    "high": 150,
}

assert check_load_manifest(
    [
        {"tag": "a", "zone": "mid", "mass": 50},
        {"tag": "b", "zone": "aft", "mass": 30},
        {"tag": "c", "zone": "aft", "mass": 20},
    ],
    PLAN,
) == {
    "loaded": ["a", "b"],
    "stopped": "c",
    "limit": "moment",
    "mass": 80,
    "moment": 120,
    "zones": [
        {"zone": "fore", "mass": 0},
        {"zone": "mid", "mass": 50},
        {"zone": "aft", "mass": 30},
    ],
}, "the moment window bites and the item is left off"

assert check_load_manifest(
    [
        {"tag": "a", "zone": "fore", "mass": 60},
        {"tag": "b", "zone": "fore", "mass": 50},
        {"tag": "c", "zone": "mid", "mass": 10},
    ],
    PLAN,
) == {
    "loaded": ["a"],
    "stopped": "b",
    "limit": "cap",
    "mass": 60,
    "moment": -120,
    "zones": [
        {"zone": "fore", "mass": 60},
        {"zone": "mid", "mass": 0},
        {"zone": "aft", "mass": 0},
    ],
}, "a zone cap is tested first and the items behind are never tried"

assert check_load_manifest(
    [{"tag": "a", "zone": "hold", "mass": 60}, {"tag": "b", "zone": "hold", "mass": 50}],
    {
        "zones": [{"zone": "hold", "cap": 1000, "arm": 0}],
        "gross": 100,
        "low": -10,
        "high": 10,
    },
) == {
    "loaded": ["a"],
    "stopped": "b",
    "limit": "gross",
    "mass": 60,
    "moment": 0,
    "zones": [{"zone": "hold", "mass": 60}],
}, "the rating bites before the moment does"

assert check_load_manifest(
    [{"tag": "a", "zone": "tail", "mass": 15}, {"tag": "b", "zone": "tail", "mass": 10}],
    {
        "zones": [{"zone": "tail", "cap": 500, "arm": -5}],
        "gross": 500,
        "low": -100,
        "high": 100,
    },
) == {
    "loaded": ["a"],
    "stopped": "b",
    "limit": "moment",
    "mass": 15,
    "moment": -75,
    "zones": [{"zone": "tail", "mass": 15}],
}, "the window bites on the low side too"

assert check_load_manifest(
    [{"tag": "a", "zone": "z", "mass": 50}],
    {"zones": [{"zone": "z", "cap": 50, "arm": 1}], "gross": 50, "low": 0, "high": 50},
) == {
    "loaded": ["a"],
    "stopped": "",
    "limit": "",
    "mass": 50,
    "moment": 50,
    "zones": [{"zone": "z", "mass": 50}],
}, "sitting exactly on every limit is not a break"

assert check_load_manifest([], PLAN) == {
    "loaded": [],
    "stopped": "",
    "limit": "",
    "mass": 0,
    "moment": 0,
    "zones": [
        {"zone": "fore", "mass": 0},
        {"zone": "mid", "mass": 0},
        {"zone": "aft", "mass": 0},
    ],
}, "an empty manifest loads nothing and breaks nothing"

assert check_load_manifest(
    [
        {"tag": "a", "zone": "fore", "mass": 40},
        {"tag": "b", "zone": "aft", "mass": 20},
        {"tag": "c", "zone": "mid", "mass": 90},
    ],
    PLAN,
)["loaded"] == ["a", "b", "c"], "a load inside every limit goes aboard entire"


def rejects(items, plan):
    try:
        check_load_manifest(items, plan)
    except ValueError:
        return True
    return False


assert rejects([], "plan"), "plan must be a record"
assert rejects([], {"zones": [], "gross": 10, "low": 0, "high": 1}), "a plan with no zones is rejected"
assert rejects([], {**PLAN, "zones": [{"zone": "", "cap": 5, "arm": 1}]}), "an empty zone name is rejected"
assert rejects(
    [],
    {
        **PLAN,
        "zones": [{"zone": "twin", "cap": 5, "arm": 1}, {"zone": "twin", "cap": 6, "arm": 2}],
    },
), "a repeated zone name is rejected"
assert rejects([], {**PLAN, "zones": [{"zone": "z", "cap": 0, "arm": 1}]}), "a cap of nought is rejected"
assert rejects(
    [], {**PLAN, "zones": [{"zone": "z", "cap": 5, "arm": 1.5}]}
), "a fractional arm is rejected"
assert rejects([], {**PLAN, "gross": 0}), "a gross of nought is rejected"
assert rejects([], {**PLAN, "low": 200}), "low above high is rejected"
assert rejects([], {**PLAN, "high": "big"}), "high must be a whole number"
assert rejects("cargo", PLAN), "items must be a list"
assert rejects([9], PLAN), "an item must be a record"
assert rejects([{"tag": "", "zone": "mid", "mass": 5}], PLAN), "an empty tag is rejected"
assert rejects(
    [{"tag": "same", "zone": "mid", "mass": 5}, {"tag": "same", "zone": "mid", "mass": 6}],
    PLAN,
), "a repeated tag is rejected"
assert rejects([{"tag": "a", "zone": "nowhere", "mass": 5}], PLAN), "an unknown zone is rejected"
assert rejects([{"tag": "a", "zone": "mid", "mass": 0}], PLAN), "a mass of nought is rejected"
print("ok")
