from solution import audit_tour_card

FLOOR = [
    {"room": "Atlas", "hop": 3, "dwell": 9, "merit": 4},
    {"room": "Bronze", "hop": 2, "dwell": 6, "merit": 5},
    {"room": "Cameos", "hop": 5, "dwell": 4, "merit": 2},
    {"room": "Drums", "hop": 1, "dwell": 7, "merit": 6},
]

assert audit_tour_card(FLOOR, ["Atlas", "Bronze"], 30) == {
    "minutes": 20,
    "merit": 9,
    "spare": 10,
    "ok": True,
}, "a card that stops early never pays for the far end of the floor"

assert audit_tour_card(FLOOR, [], 5) == {
    "minutes": 0,
    "merit": 0,
    "spare": 5,
    "ok": True,
}, "a blank card costs nothing at all"

assert audit_tour_card(FLOOR, ["Drums"], 18) == {
    "minutes": 18,
    "merit": 6,
    "spare": 0,
    "ok": True,
}, "spending the allowance to the minute still sits within it"

assert audit_tour_card(FLOOR, ["Atlas", "Bronze", "Cameos", "Drums"], 20) == {
    "minutes": 37,
    "merit": 17,
    "spare": -17,
    "ok": False,
}, "a card past the allowance reports how far past"

assert audit_tour_card(FLOOR, ["Cameos"], 100) == {
    "minutes": 14,
    "merit": 2,
    "spare": 86,
    "ok": True,
}, "reaching one room deep pays for the doorways walked through"

assert audit_tour_card(FLOOR, ["Atlas", "Drums"], 27) == {
    "minutes": 27,
    "merit": 10,
    "spare": 0,
    "ok": True,
}, "rooms skipped in the middle are still walked past"

assert audit_tour_card([{"room": "Solo", "hop": 0, "dwell": 1, "merit": 0}], [], 0) == {
    "minutes": 0,
    "merit": 0,
    "spare": 0,
    "ok": True,
}, "a blank card against no allowance is still within it"


def rejects(rooms, card, allowance):
    try:
        audit_tour_card(rooms, card, allowance)
    except ValueError:
        return True
    return False


assert rejects("Atlas", [], 10), "a rooms argument that is not a list is rejected"
assert rejects(FLOOR, "Atlas", 10), "a card that is not a list is rejected"
assert rejects(FLOOR, ["Enamel"], 10), "a card naming no room is rejected"
assert rejects(FLOOR, ["Atlas", "Atlas"], 10), "a card repeating a name is rejected"
assert rejects(FLOOR, ["Bronze", "Atlas"], 10), "a card out of floor-plan order is rejected"
assert rejects(FLOOR, [7], 10), "a card entry that is not a string is rejected"
assert rejects(
    [{"room": "Atlas", "hop": 1, "dwell": 2}], [], 10
), "a room missing a key is rejected"
assert rejects(
    [{"room": "Atlas", "hop": -1, "dwell": 2, "merit": 0}], [], 10
), "a hop below nought is rejected"
assert rejects(
    [{"room": "Atlas", "hop": 1, "dwell": 0, "merit": 0}], [], 10
), "a dwell below one is rejected"
assert rejects(
    [{"room": "Atlas", "hop": 1, "dwell": 2, "merit": -1}], [], 10
), "a merit below nought is rejected"
assert rejects(
    [
        {"room": "Atlas", "hop": 1, "dwell": 2, "merit": 0},
        {"room": "Atlas", "hop": 1, "dwell": 2, "merit": 0},
    ],
    [],
    10,
), "a floor repeating a room name is rejected"
assert rejects(FLOOR, [], -4), "an allowance below nought is rejected"
print("ok")
