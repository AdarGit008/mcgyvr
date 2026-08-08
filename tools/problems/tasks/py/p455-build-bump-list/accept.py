from solution import build_bump_list


def flier(code, fare, miles, checked):
    return {"code": code, "fare": fare, "miles": miles, "checked": checked}


roll = [
    flier("ann", "saver", 500, 3),
    flier("bob", "flex", 10, 5),
    flier("cid", "award", 900, 1),
    flier("dot", "saver", 500, 2),
]

assert build_bump_list(roll, 9, []) == {"boarding": ["bob", "dot", "ann", "cid"], "bumped": []}, (
    "a roomier aeroplane bumps nobody and still ranks the roll"
)
assert build_bump_list(roll, 4, []) == {"boarding": ["bob", "dot", "ann", "cid"], "bumped": []}, (
    "seats exactly matching the roll bump nobody"
)
assert build_bump_list(roll, 3, []) == {"boarding": ["bob", "dot", "ann"], "bumped": ["cid"]}, (
    "one seat short drops the least protected"
)
assert build_bump_list(roll, 2, []) == {"boarding": ["bob", "dot"], "bumped": ["cid", "ann"]}, (
    "two seats short works up from the bottom"
)
assert build_bump_list(roll, 3, ["bob"]) == {"boarding": ["dot", "ann", "cid"], "bumped": ["bob"]}, (
    "a volunteer goes ahead of the least protected"
)
assert build_bump_list(roll, 3, ["bob", "cid"]) == {"boarding": ["dot", "ann", "cid"], "bumped": ["bob"]}, (
    "only as many volunteers are taken as seats are missing"
)
assert build_bump_list(roll, 4, ["bob"]) == {"boarding": ["bob", "dot", "ann", "cid"], "bumped": []}, (
    "with seats for everyone the offer is not taken up"
)
assert build_bump_list(roll, 2, ["bob"]) == {"boarding": ["dot", "ann"], "bumped": ["bob", "cid"]}, (
    "a volunteer covers part of the shortfall and ranking covers the rest"
)
assert build_bump_list(roll, 3, ["cid"]) == {"boarding": ["bob", "dot", "ann"], "bumped": ["cid"]}, (
    "a volunteer who was going anyway is not counted twice"
)
assert build_bump_list(roll, 0, []) == {"boarding": [], "bumped": ["cid", "ann", "dot", "bob"]}, (
    "an aeroplane with no seats leaves the whole roll behind, worst first"
)
assert build_bump_list([], 3, []) == {"boarding": [], "bumped": []}, "an empty roll boards nobody"
assert build_bump_list([flier("p", "saver", 700, 9), flier("q", "saver", 700, 4)], 1, []) == {
    "boarding": ["q"],
    "bumped": ["p"],
}, "equal miles are broken by the earlier check-in"
assert build_bump_list([flier("p", "flex", 0, 9), flier("q", "award", 9999, 1)], 1, []) == {
    "boarding": ["p"],
    "bumped": ["q"],
}, "the fare outranks any pile of miles"


def rejects(travellers, seats, volunteers):
    try:
        build_bump_list(travellers, seats, volunteers)
    except ValueError:
        return True
    return False


assert rejects("no", 1, []), "a roll that is not a list is refused"
assert rejects([], -1, []), "a negative seat count is refused"
assert rejects([], 1.5, []), "a fractional seat count is refused"
assert rejects([], 1, "ann"), "volunteers that are not a list are refused"
assert rejects([[1]], 1, []), "a traveller that is not a record is refused"
assert rejects([flier("", "flex", 1, 1)], 1, []), "an empty code is refused"
assert rejects([flier("a", "flex", 1, 1), flier("a", "flex", 1, 2)], 1, []), "one code carried twice is refused"
assert rejects([flier("a", "gold", 1, 1)], 1, []), "an unknown fare is refused"
assert rejects([flier("a", "flex", -1, 1)], 1, []), "negative miles are refused"
assert rejects([flier("a", "flex", 1, 0)], 1, []), "a check-in of nought is refused"
assert rejects([flier("a", "flex", 1, 2), flier("b", "flex", 1, 2)], 1, []), (
    "two travellers at one check-in are refused"
)
assert rejects([flier("a", "flex", 1, 1)], 1, ["zz"]), "a volunteer nobody answers to is refused"
assert rejects([flier("a", "flex", 1, 1), flier("b", "flex", 1, 2)], 1, ["a", "a"]), (
    "a volunteer named twice is refused"
)
print("ok")
