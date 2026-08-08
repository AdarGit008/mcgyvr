from solution import stage_attrition

stages = [
    {"stage": "mass-floor", "field": "mass", "low": 10, "high": None},
    {"stage": "span-band", "field": "span", "low": 5, "high": 9},
    {"stage": "purity-cap", "field": "purity", "low": None, "high": 80},
]
assert stage_attrition(
    [
        {"mass": 12, "span": 7, "purity": 50},
        {"mass": 5, "span": 1, "purity": 99},
        {"mass": 20, "span": 4, "purity": 99},
        {"mass": 15, "span": 9, "purity": 81},
        {"mass": 15, "purity": 10},
    ],
    stages,
) == [
    ["mass-floor", 1],
    ["span-band", 2],
    ["purity-cap", 1],
    ["through", 1],
], "each specimen counts once, at its first failing stage"
assert stage_attrition([{"mass": 10, "span": 5, "purity": 80}], stages) == [
    ["mass-floor", 0],
    ["span-band", 0],
    ["purity-cap", 0],
    ["through", 1],
], "bounds are inclusive at both ends"
assert stage_attrition([], stages) == [
    ["mass-floor", 0],
    ["span-band", 0],
    ["purity-cap", 0],
    ["through", 0],
], "an empty line counts nothing"
assert stage_attrition([{"mass": 1}, {"mass": 2}], []) == [
    ["through", 2]
], "no stages, everything is through"
assert stage_attrition(
    [{"mass": "heavy"}],
    [{"stage": "mass-floor", "field": "mass", "low": None, "high": None}],
) == [["mass-floor", 1], ["through", 0]], "a non-number field fails its stage"


def rejects(specimens, stages_arg):
    try:
        stage_attrition(specimens, stages_arg)
    except ValueError:
        return True
    return False


assert rejects([], [{"stage": "", "field": "a", "low": None, "high": None}]), "empty stage name is rejected"
assert rejects(
    [],
    [
        {"stage": "x", "field": "a", "low": None, "high": None},
        {"stage": "x", "field": "b", "low": None, "high": None},
    ],
), "repeated stage name is rejected"
assert rejects([], [{"stage": "through", "field": "a", "low": None, "high": None}]), "a stage named through is rejected"
assert rejects([], [{"stage": "x", "field": "a", "low": 9, "high": 2}]), "reversed bounds are rejected"
print("ok")
