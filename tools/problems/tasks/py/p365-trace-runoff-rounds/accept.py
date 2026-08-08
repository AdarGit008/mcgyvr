from solution import trace_runoff_rounds


def repeat(paper, times):
    return [list(paper) for _ in range(times)]


def rejects(papers):
    try:
        trace_runoff_rounds(papers)
    except ValueError:
        return True
    return False


assert trace_runoff_rounds([["kite"], ["kite"], ["drum"]]) == [
    "1|kite=2,drum=1|won:kite"
], "one round is enough when a runner already passes half"

assert trace_runoff_rounds([["one"], ["one"]]) == [
    "1|one=2|won:one"
], "a race of one closes immediately"

assert trace_runoff_rounds([["a", "b"], ["b", "a"], ["c", "a"]]) == [
    "1|a=1,b=1,c=1|out:c",
    "2|a=2,b=1|won:a",
], "an opening-round tie falls to the runner met last"

assert trace_runoff_rounds([["a"], ["b"], ["c"]]) == [
    "1|a=1,b=1,c=1|out:c",
    "2|a=1,b=1|out:b",
    "3|a=1|won:a",
], "papers set aside shrink the half the tally must pass"

assert trace_runoff_rounds(
    repeat(["a"], 8)
    + repeat(["b", "a"], 3)
    + repeat(["c"], 4)
    + [["d", "b"], ["d"]]
) == [
    "1|a=8,c=4,b=3,d=2|out:d",
    "2|a=8,b=4,c=4|out:b",
    "3|a=11,c=4|won:a",
], "a bottom tie is settled by the round before, not by the names"

assert trace_runoff_rounds(
    repeat(["red", "blue"], 3)
    + repeat(["blue", "red"], 2)
    + repeat(["gold", "blue"], 2)
) == [
    "1|red=3,blue=2,gold=2|out:gold",
    "2|blue=4,red=3|won:blue",
], "the runner ahead in the opening round can be overtaken"

assert trace_runoff_rounds(
    [
        ["p", "q", "r"],
        ["p", "q", "r"],
        ["q", "r", "p"],
        ["r", "q", "p"],
        ["r", "p", "q"],
    ]
) == [
    "1|p=2,r=2,q=1|out:q",
    "2|r=3,p=2|won:r",
], "falling tally leads the line and first-met order settles the rest"

assert rejects([]), "a race with no papers is rejected"
assert rejects([[]]), "an empty paper is rejected"
assert rejects([["a", "a"]]), "a runner named twice on one paper is rejected"
assert rejects([["a"], [""]]), "an empty runner name is rejected"
assert rejects([["a=b"]]), "a name holding an equals sign is rejected"
assert rejects([["a|b"]]), "a name holding a bar is rejected"
assert rejects([["a,b"]]), "a name holding a comma is rejected"
assert rejects([["a"], 5]), "a paper that is not a list is rejected"
assert rejects("papers"), "an argument that is not a list is rejected"
print("ok")
