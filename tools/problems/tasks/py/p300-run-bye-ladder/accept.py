from solution import run_bye_ladder


def rejects(seeds, upsets):
    try:
        run_bye_ladder(seeds, upsets)
    except ValueError:
        return True
    return False


assert run_bye_ladder(["x", "y"], []) == {
    "rounds": [{"bye": None, "matches": [["x", "y"]]}],
    "champion": "x",
}, "two entrants meet once and the stronger seed takes it"
assert run_bye_ladder(["x", "y"], ["y"]) == {
    "rounds": [{"bye": None, "matches": [["x", "y"]]}],
    "champion": "y",
}, "a named upset turns the only match around"
assert run_bye_ladder(["a", "b", "c", "d"], []) == {
    "rounds": [
        {"bye": None, "matches": [["a", "d"], ["b", "c"]]},
        {"bye": None, "matches": [["a", "b"]]},
    ],
    "champion": "a",
}, "an even field meets head to tail and never sits anybody out"
assert run_bye_ladder(["p", "q", "r"], []) == {
    "rounds": [
        {"bye": "p", "matches": [["q", "r"]]},
        {"bye": None, "matches": [["p", "q"]]},
    ],
    "champion": "p",
}, "three entrants sit the strongest out of the opening round"
assert run_bye_ladder(["ana", "bo", "cy", "dee", "eli"], []) == {
    "rounds": [
        {"bye": "ana", "matches": [["bo", "eli"], ["cy", "dee"]]},
        {"bye": "bo", "matches": [["ana", "cy"]]},
        {"bye": None, "matches": [["ana", "bo"]]},
    ],
    "champion": "ana",
}, "the second sit-out passes over the one who already sat"
assert run_bye_ladder(["ana", "bo", "cy", "dee", "eli"], ["eli", "cy"]) == {
    "rounds": [
        {"bye": "ana", "matches": [["bo", "eli"], ["cy", "dee"]]},
        {"bye": "cy", "matches": [["ana", "eli"]]},
        {"bye": None, "matches": [["cy", "eli"]]},
    ],
    "champion": "eli",
}, "an upset carries the weakest seed all the way up"

field = [f"t{n:02d}" for n in range(1, 18)]
long_run = run_bye_ladder(field, [])
assert len(long_run["rounds"]) == 5, "seventeen entrants take five rounds"
assert long_run["rounds"][0]["bye"] == "t01", (
    "the strongest sits the first round out"
)
assert len(long_run["rounds"][0]["matches"]) == 8, "sixteen play eight matches"
assert long_run["rounds"][0]["matches"][0] == ["t02", "t17"], "head meets tail"
assert [long_run["rounds"][1]["bye"], long_run["rounds"][2]["bye"]] == [
    "t02",
    "t03",
], "the sit-out walks down the seeds while fresh ones remain"
assert long_run["rounds"][3] == {"bye": "t01", "matches": [["t02", "t03"]]}, (
    "with all three having sat before, the strongest sits again"
)
assert long_run["rounds"][4] == {"bye": None, "matches": [["t01", "t02"]]}, (
    "the final is even and needs no sitter"
)
assert long_run["champion"] == "t01", "no upsets means the top seed wins"

assert rejects("ab", []), "the seeds are a list"
assert rejects(["a", "b"], "a"), "the upsets are a list"
assert rejects(["a"], []), "one entrant is no ladder"
assert rejects(["a", 2], []), "a name is a string"
assert rejects(["a", "a"], []), "a name is entered once"
assert rejects(["a", "b"], ["z"]), "z is no entrant"
assert rejects(["a", "b"], ["b", "b"]), "an upset is named once"
print("ok")
