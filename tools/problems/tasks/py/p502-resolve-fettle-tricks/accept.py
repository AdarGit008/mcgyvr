from solution import resolve_fettle_tricks

assert resolve_fettle_tricks(
    {"trump": "f", "tricks": [["b5", "b13", "f2", "b1"], ["c3", "c1", "c7", "b2"]]}
) == {"takers": [2, 3], "worths": [9, 8], "even": 9, "odd": 8}, "a lone trump takes the trick"
assert resolve_fettle_tricks({"trump": "none", "tricks": [["l4", "l9", "c13", "b1"]]}) == {
    "takers": [1],
    "worths": [12],
    "even": 0,
    "odd": 12,
}, "with no trump only the called house can take"
assert resolve_fettle_tricks({"trump": "b", "tricks": [["b13", "b1", "c2", "f3"]]}) == {
    "takers": [1],
    "worths": [12],
    "even": 0,
    "odd": 12,
}, "a 1 outranks a 13 in the same house"
assert resolve_fettle_tricks(
    {
        "trump": "l",
        "tricks": [["c4", "c11", "c12", "c6"], ["c10", "l3", "f13", "b1"], ["f4", "f5", "f6", "f7"]],
    }
) == {"takers": [2, 3, 2], "worths": [5, 10, 3], "even": 8, "odd": 10}, "the leader rotates"
assert resolve_fettle_tricks({"trump": "none", "tricks": [["b2", "c3", "f4", "l5"]]}) == {
    "takers": [0],
    "worths": [3],
    "even": 3,
    "odd": 0,
}, "a trick of four houses goes to the seat that called it"
assert resolve_fettle_tricks({"trump": "c", "tricks": [["f8", "f12", "c1", "c13"]]}) == {
    "takers": [2],
    "worths": [15],
    "even": 15,
    "odd": 0,
}, "the strongest trump beats a weaker trump laid after it"


def rejects(deal):
    try:
        resolve_fettle_tricks(deal)
    except ValueError:
        return True
    return False


assert rejects([]), "a list is not a deal"
assert rejects({"trump": "x", "tricks": [["b1", "b2", "b3", "b4"]]}), "unknown trump house"
assert rejects({"trump": "b", "tricks": []}), "an empty deal is refused"
assert rejects({"trump": "b", "tricks": [["b1", "b2", "b3"]]}), "a trick of three cards"
assert rejects({"trump": "b", "tricks": [["b01", "b2", "b3", "b4"]]}), "a padding zero"
assert rejects({"trump": "b", "tricks": [["b14", "b2", "b3", "b4"]]}), "a strength above 13"
assert rejects(
    {"trump": "b", "tricks": [["b1", "b2", "b3", "b4"], ["b5", "b6", "b7", "b1"]]}
), "a card laid twice in the deal"
print("ok")
