from solution import pick_build

assert pick_build("3:9", [1, 4, 8, 12]) == 8, "largest offer inside the clause"
assert pick_build("3:9^8", [1, 4, 8, 12]) == 4, "a carve-out shuts one build out"
assert pick_build(":5,10:", [6, 7]) == -1, "offers falling between clauses lose"
assert pick_build(":", [0]) == 0, "the everything clause admits build 0"
assert pick_build("10:^12", [12]) == -1, "a carve-out works in an open-ended clause"
assert pick_build("0:5^4,4:9", [4]) == 4, "a build carved from one clause may enter by another"
assert pick_build("2:3", []) == -1, "no offers, no pick"
assert pick_build(":4,20:30", [25, 3, 19]) == 25, "the winner may come from any clause"


def rejects(gate, offers):
    try:
        pick_build(gate, offers)
    except ValueError:
        return True
    return False


assert rejects("9:3", [1]), "ends out of order are rejected"
assert rejects("3:9^20", [1]), "an uncovered carve-out is rejected"
assert rejects("", [1]), "a gate with no clause is rejected"
assert rejects("3-9", [1]), "a malformed clause is rejected"
assert rejects("03:9", [1]), "a leading zero is rejected"
assert rejects("3:9", [-2]), "a negative offer is rejected"
assert rejects("3:9", [2.5]), "a fractional offer is rejected"
assert rejects(7, [1]), "a non-string gate is rejected"
print("ok")
