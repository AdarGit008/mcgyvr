from solution import critical_chain_name


def rejects(value):
    try:
        critical_chain_name(value)
    except ValueError:
        return True
    return False


assert (
    critical_chain_name(
        [
            {"label": "a", "hours": 3, "needs": []},
            {"label": "b", "hours": 2, "needs": ["a"]},
            {"label": "c", "hours": 4, "needs": ["a"]},
            {"label": "d", "hours": 1, "needs": ["b", "c"]},
        ]
    )
    == "a>c>d"
), "the heavier arm of a diamond"
assert critical_chain_name([{"label": "solo", "hours": 5, "needs": []}]) == "solo", (
    "one step is its own run"
)
assert (
    critical_chain_name(
        [
            {"label": "x", "hours": 2, "needs": []},
            {"label": "y", "hours": 5, "needs": []},
        ]
    )
    == "y"
), "two steps with nothing linking them"
assert (
    critical_chain_name(
        [
            {"label": "zip", "hours": 1, "needs": []},
            {"label": "arc", "hours": 2, "needs": ["zip"]},
            {"label": "mid", "hours": 3, "needs": ["arc"]},
        ]
    )
    == "zip>arc>mid"
), "a run reported in link order, not list order"
assert (
    critical_chain_name(
        [
            {"label": "p", "hours": 1, "needs": []},
            {"label": "q", "hours": 2, "needs": ["p"]},
            {"label": "r", "hours": 2, "needs": ["p"]},
        ]
    )
    == "p>q"
), "equal weights settled by the labels"
assert (
    critical_chain_name(
        [
            {"label": "aa", "hours": 4, "needs": []},
            {"label": "ab", "hours": 1, "needs": []},
            {"label": "ac", "hours": 3, "needs": ["ab"]},
        ]
    )
    == "aa"
), "a one-step run can beat a two-step run of the same weight"

assert rejects("a"), "not a list"
assert rejects([]), "an empty job"
assert rejects(["a"]), "a step that is not a mapping"
assert rejects([{"label": "", "hours": 1, "needs": []}]), "an empty label"
assert rejects(
    [
        {"label": "a", "hours": 1, "needs": []},
        {"label": "a", "hours": 2, "needs": []},
    ]
), "two steps with the same label"
assert rejects([{"label": "a", "hours": 0, "needs": []}]), "zero hours"
assert rejects([{"label": "a", "hours": 2.5, "needs": []}]), "fractional hours"
assert rejects([{"label": "a", "hours": 1, "needs": "b"}]), (
    "a needs list that is not a list"
)
assert rejects([{"label": "a", "hours": 1, "needs": ["ghost"]}]), (
    "a needs entry matching nothing"
)
assert rejects([{"label": "a", "hours": 1, "needs": ["a"]}]), "a step needing itself"
assert rejects(
    [
        {"label": "a", "hours": 1, "needs": ["b"]},
        {"label": "b", "hours": 1, "needs": ["a"]},
    ]
), "a ring"
print("ok")
