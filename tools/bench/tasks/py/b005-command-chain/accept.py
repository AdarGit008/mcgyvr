from solution import chain_of_command, headcount, widest_team

org = {
    "name": "avery",
    "reports": [
        {
            "name": "birch",
            "reports": [
                {"name": "casey", "reports": []},
                {"name": "dana", "reports": [{"name": "elm", "reports": []}]},
            ],
        },
        {"name": "fern", "reports": []},
    ],
}

assert chain_of_command(org, "avery") == ["avery"], "the head alone"
assert chain_of_command(org, "elm") == [
    "avery",
    "birch",
    "dana",
    "elm",
], "a deep chain"
assert chain_of_command(org, "fern") == ["avery", "fern"], "a direct report"
assert chain_of_command(org, "casey") == [
    "avery",
    "birch",
    "casey",
], "a leaf under the first branch"


def rejects(*args):
    try:
        chain_of_command(*args)
    except ValueError:
        return True
    return False


assert rejects(org, "zoe"), "absent person is rejected"
assert rejects(
    {"name": "dot", "reports": [{"name": "dot", "reports": []}]}, "dot"
), "a duplicated person is rejected"
assert rejects(
    {"name": "ok", "reports": [{"name": "", "reports": []}]}, "ok"
), "an empty name anywhere is rejected"
assert rejects(org, ""), "empty person is rejected"
assert rejects(org, 42), "non-string person is rejected"
assert headcount(org) == 6, "headcount of the whole chart"
assert widest_team(org) == 2, "widest team in the chart"
assert widest_team({"name": "solo", "reports": []}) == 0, "widest team of one"
print("ok")
