from solution import divide_delegates


def slate(name, votes, roster):
    return {"name": name, "votes": votes, "roster": roster}


def rejects(slates, delegates):
    try:
        divide_delegates(slates, delegates)
    except ValueError:
        return True
    return False


assert divide_delegates(
    [slate("ash", 720, 10), slate("bay", 180, 10), slate("cob", 100, 10)], 10
) == {"ash": 7, "bay": 2, "cob": 1}, "the leftover delegate goes to the largest leftover"

assert divide_delegates(
    [slate("zeta", 35, 10), slate("alpha", 25, 10), slate("mid", 40, 10)], 10
) == {
    "zeta": 4,
    "alpha": 2,
    "mid": 4,
}, "a level leftover is settled by the vote count, not the name"

assert divide_delegates(
    [slate("yew", 45, 10), slate("ash", 45, 10), slate("elm", 10, 10)], 10
) == {
    "yew": 5,
    "ash": 4,
    "elm": 1,
}, "level leftovers and level votes fall to the earlier slate"

assert divide_delegates(
    [slate("big", 800, 3), slate("wee", 100, 10), slate("tot", 100, 10)], 10
) == {
    "big": 3,
    "wee": 4,
    "tot": 3,
}, "delegates freed by a roster are reckoned again, not lost"

assert divide_delegates(
    [slate("a", 600, 2), slate("b", 300, 3), slate("c", 100, 10)], 10
) == {"a": 2, "b": 3, "c": 5}, "pinning one slate can push the next above its own roster"

assert divide_delegates([slate("north", 500, 10), slate("south", 500, 10)], 4) == {
    "north": 2,
    "south": 2,
}, "an exact split leaves nothing over to pass around"

assert divide_delegates([slate("lone", 7, 5)], 5) == {
    "lone": 5
}, "one slate takes the whole convention"

assert divide_delegates([slate("cap", 900, 1), slate("rest", 100, 9)], 9) == {
    "cap": 1,
    "rest": 8,
}, "a slate held to one leaves the remainder to the others"

assert rejects([], 3), "no slates at all is rejected"
assert rejects([slate("a", 5, 5)], 0), "a delegate count of zero is rejected"
assert rejects([slate("a", 5, 5)], 1.5), "a fractional delegate count is rejected"
assert rejects([slate("", 5, 5)], 2), "an empty slate name is rejected"
assert rejects(
    [slate("a", 5, 5), slate("a", 4, 5)], 2
), "two slates sharing a name are rejected"
assert rejects([slate("a", 0, 5)], 2), "a slate with no votes is rejected"
assert rejects([slate("a", 5, 0)], 2), "a roster of zero is rejected"
assert rejects(
    [slate("a", 5, 2), slate("b", 5, 2)], 5
), "rosters too small for the convention are rejected"
assert rejects(["a slate"], 2), "a slate that is not a mapping is rejected"
assert rejects("slates", 2), "slates that are not a list are rejected"
print("ok")
