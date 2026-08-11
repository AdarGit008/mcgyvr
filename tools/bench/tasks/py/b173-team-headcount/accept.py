from solution import team_headcount

shift = {"ada": ["bo", "cy"], "bo": ["di"], "cy": [], "di": []}
bench = {"lead": ["mix", "prove", "bake"], "mix": [], "prove": [], "bake": []}
chain = {"a1": ["a2"], "a2": ["a3"], "a3": ["a4"], "a4": []}

assert team_headcount(shift, "ada") == 4, "the top name covers the whole chart"
assert team_headcount(shift, "bo") == 2, "a middle name covers itself and its one report"
assert team_headcount(shift, "cy") == 1, "a worker who leads nobody covers only themselves"
assert team_headcount(shift, "di") == 1, "the deepest name covers only themselves"
assert team_headcount(bench, "lead") == 4, "three direct reports and no depth still count"
assert team_headcount(chain, "a1") == 4, "a chart four levels deep is counted to the bottom"
assert team_headcount(chain, "a3") == 2, "counting starts partway down the chain"


def rejects(chart, name):
    try:
        team_headcount(chart, name)
    except ValueError:
        return True
    return False


assert rejects("ada", "ada"), "a chart that is not a mapping is rejected"
assert rejects(shift, "zoe"), "a name outside the chart is rejected"
assert rejects({"solo": "nobody"}, "solo"), "reports that are not a list are rejected"
assert rejects({"lead": [7]}, "lead"), "a report that is not a name is rejected"
print("ok")
