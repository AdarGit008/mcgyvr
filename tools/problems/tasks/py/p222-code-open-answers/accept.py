from solution import code_open_answers

RULES = [
    {"code": "PRICE", "phrase": "too dear"},
    {"code": "PRICE", "phrase": "costs a lot"},
    {"code": "WAIT", "phrase": "queue"},
    {"code": "STAFF", "phrase": "rude staff"},
]


def rejects(rules, answers):
    try:
        code_open_answers(rules, answers)
    except ValueError:
        return True
    return False


assert code_open_answers([{"code": "A", "phrase": "bus"}], ["The bus was late"]) == {
    "tally": [{"code": "A", "count": 1}],
    "loose": [],
}, "one rule taking one answer"

assert code_open_answers(RULES, ["Far too dear!", "Costs a lot, honestly"]) == {
    "tally": [
        {"code": "PRICE", "count": 2},
        {"code": "WAIT", "count": 0},
        {"code": "STAFF", "count": 0},
    ],
    "loose": [],
}, "two phrases feeding one code, and the untouched codes still listed"

assert code_open_answers(RULES, ["Nothing at all to report"]) == {
    "tally": [
        {"code": "PRICE", "count": 0},
        {"code": "WAIT", "count": 0},
        {"code": "STAFF", "count": 0},
    ],
    "loose": ["nothing at all to report"],
}, "an answer nothing takes is reported tidied"

assert code_open_answers(
    [{"code": "FIRST", "phrase": "long queue"}, {"code": "SECOND", "phrase": "queue"}],
    ["a long queue outside"],
) == {
    "tally": [{"code": "FIRST", "count": 1}, {"code": "SECOND", "count": 0}],
    "loose": [],
}, "the earlier rule wins when both would take the answer"

assert code_open_answers([{"code": "Q", "phrase": "queue"}], ["QUEUEING for ages"]) == {
    "tally": [{"code": "Q", "count": 0}],
    "loose": ["queueing for ages"],
}, "a phrase matches whole words, never a word's opening"

assert code_open_answers([{"code": "Q", "phrase": "rude staff"}], ["  rude,,,STAFF  "]) == {
    "tally": [{"code": "Q", "count": 1}],
    "loose": [],
}, "punctuation between the words collapses to the one space"

assert code_open_answers([{"code": "Q", "phrase": "bus"}], ["!!!", "bus"]) == {
    "tally": [{"code": "Q", "count": 1}],
    "loose": [""],
}, "an answer that tidies away to nothing is loose and empty"

assert code_open_answers([{"code": "Q", "phrase": "bus"}], []) == {
    "tally": [{"code": "Q", "count": 0}],
    "loose": [],
}, "no answers leaves every count at zero"

assert code_open_answers([{"code": "N9", "phrase": "route 9"}], ["Route 9 again"]) == {
    "tally": [{"code": "N9", "count": 1}],
    "loose": [],
}, "digits count as ordinary phrase characters"

assert code_open_answers(
    [{"code": "R", "phrase": "no lift"}], ["lift no good", "no lift"]
) == {
    "tally": [{"code": "R", "count": 1}],
    "loose": ["lift no good"],
}, "the phrase words must run consecutively and in order"

assert rejects([], ["x"]), "an empty rule list is rejected"
assert rejects("rules", ["x"]), "rules that are not a list are rejected"
assert rejects([["A", "bus"]], ["x"]), "a rule that is not a mapping is rejected"
assert rejects([{"code": "", "phrase": "bus"}], ["x"]), "an empty code is rejected"
assert rejects([{"code": "A", "phrase": "Bus"}], ["x"]), "an uppercase phrase is rejected"
assert rejects([{"code": "A", "phrase": "a  b"}], ["x"]), "a doubled space in a phrase is rejected"
assert rejects([{"code": "A", "phrase": ""}], ["x"]), "an empty phrase is rejected"
assert rejects(
    [{"code": "A", "phrase": "bus"}, {"code": "B", "phrase": "bus"}], ["x"]
), "two rules sharing a phrase are rejected"
assert rejects([{"code": "A", "phrase": "bus"}], "x"), "answers that are not a list are rejected"
assert rejects([{"code": "A", "phrase": "bus"}], [7]), "an answer that is not a string is rejected"

print("ok")
