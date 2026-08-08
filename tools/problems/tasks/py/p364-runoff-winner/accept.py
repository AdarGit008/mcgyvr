from solution import runoff_winner


def rejects(ballots):
    try:
        runoff_winner(ballots)
    except ValueError:
        return True
    return False


assert runoff_winner([["a"], ["a"], ["b"]]) == "a", (
    "a first-round majority ends it at once"
)
assert runoff_winner([["solo"], ["solo"]]) == "solo", "a lone option wins unopposed"
assert (
    runoff_winner(
        [["x", "z"], ["x", "z"], ["y", "z"], ["y", "z"], ["z", "x"]]
    )
    == "x"
), "the dropped option's ballot moves to its next standing choice"
assert runoff_winner([["p", "r"], ["q", "r"], ["r", "p"]]) == "p", (
    "a three-way bottom tie drops the greatest name"
)
assert runoff_winner([["a"], ["b"], ["c", "a"], ["c", "a"]]) == "c", (
    "a spent ballot shrinks the count the majority is measured against"
)
assert runoff_winner([["a"], ["b"], ["c"]]) == "a", (
    "rounds keep going while every ballot spends itself"
)
assert (
    runoff_winner([["a", "b"], ["c", "b"], ["d", "b"], ["a", "b"]]) == "a"
), "an option nobody put first is at the bottom with zero"
assert (
    runoff_winner(
        [
            ["a"],
            ["a"],
            ["a"],
            ["a"],
            ["a"],
            ["b", "c"],
            ["b", "c"],
            ["b", "c"],
            ["c", "b"],
            ["c", "b"],
            ["c", "b"],
            ["c", "b"],
        ]
    )
    == "c"
), "the option ahead after the first round can still lose"

assert rejects([]), "no ballots at all is rejected"
assert rejects([[]]), "an empty ballot is rejected"
assert rejects([["a", "a"]]), "an option named twice on one ballot is rejected"
assert rejects([["a", ""]]), "an empty option name is rejected"
assert rejects([["a"], "b"]), "a ballot that is not a list is rejected"
assert rejects("nope"), "an argument that is not a list is rejected"
print("ok")
