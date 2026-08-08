from solution import audit_deck_load

DECK = {
    "bays": [
        {"bay": "nose", "hold": 60, "lever": -3, "pull": 150},
        {"bay": "core", "hold": 200, "lever": 0, "pull": 50},
        {"bay": "tail", "hold": 80, "lever": 6, "pull": 300},
    ],
    "total": 250,
}

assert audit_deck_load(
    [
        {"crate": "c1", "bay": "core", "weight": 100},
        {"crate": "c2", "bay": "nose", "weight": 20},
        {"crate": "c3", "bay": "tail", "weight": 40},
    ],
    DECK,
) == {
    "verdict": "clear",
    "bay": "",
    "limit": "",
    "weight": 160,
    "swing": 180,
}, "a sound load reports the deck's weight and its swings added together"

assert audit_deck_load(
    [
        {"crate": "c1", "bay": "tail", "weight": 90},
        {"crate": "c2", "bay": "nose", "weight": 70},
    ],
    DECK,
) == {
    "verdict": "broken",
    "bay": "nose",
    "limit": "hold",
    "weight": 160,
    "swing": 330,
}, "the deck's own order decides which failing bay is named"

assert audit_deck_load([{"crate": "k", "bay": "nose", "weight": 55}], DECK) == {
    "verdict": "broken",
    "bay": "nose",
    "limit": "pull",
    "weight": 55,
    "swing": -165,
}, "a swing is judged with its sign disregarded"

assert audit_deck_load(
    [
        {"crate": "c1", "bay": "nose", "weight": 50},
        {"crate": "c2", "bay": "core", "weight": 190},
        {"crate": "c3", "bay": "tail", "weight": 40},
    ],
    DECK,
) == {
    "verdict": "broken",
    "bay": "",
    "limit": "total",
    "weight": 280,
    "swing": 90,
}, "total is only reached once every bay has come through"

assert audit_deck_load([{"crate": "big", "bay": "core", "weight": 200}], DECK) == {
    "verdict": "clear",
    "bay": "",
    "limit": "",
    "weight": 200,
    "swing": 0,
}, "standing exactly on a rating is not a failure"

assert audit_deck_load([], DECK) == {
    "verdict": "clear",
    "bay": "",
    "limit": "",
    "weight": 0,
    "swing": 0,
}, "an empty deck breaks nothing and swings nothing"

assert (
    audit_deck_load([{"crate": "t", "bay": "tail", "weight": 81}], DECK)["limit"]
    == "hold"
), "hold is tested before pull within one bay"


def rejects(rows, deck):
    try:
        audit_deck_load(rows, deck)
    except ValueError:
        return True
    return False


assert rejects([], "deck"), "deck must be a record"
assert rejects([], {"bays": [], "total": 5}), "a deck with no bays is rejected"
assert rejects(
    [], {**DECK, "bays": [{"bay": "", "hold": 5, "lever": 1, "pull": 5}]}
), "an empty bay name is rejected"
assert rejects(
    [],
    {
        **DECK,
        "bays": [
            {"bay": "twin", "hold": 5, "lever": 1, "pull": 5},
            {"bay": "twin", "hold": 6, "lever": 2, "pull": 6},
        ],
    },
), "a repeated bay name is rejected"
assert rejects(
    [], {**DECK, "bays": [{"bay": "z", "hold": 0, "lever": 1, "pull": 5}]}
), "a hold of nought is rejected"
assert rejects(
    [], {**DECK, "bays": [{"bay": "z", "hold": 5, "lever": 1, "pull": 0}]}
), "a pull of nought is rejected"
assert rejects(
    [], {**DECK, "bays": [{"bay": "z", "hold": 5, "lever": 0.5, "pull": 5}]}
), "a fractional lever is rejected"
assert rejects([], {**DECK, "total": 0}), "a total of nought is rejected"
assert rejects("rows", DECK), "rows must be a list"
assert rejects([3], DECK), "a row must be a record"
assert rejects([{"crate": "", "bay": "core", "weight": 5}], DECK), "an empty crate is rejected"
assert rejects(
    [
        {"crate": "same", "bay": "core", "weight": 5},
        {"crate": "same", "bay": "core", "weight": 6},
    ],
    DECK,
), "a repeated crate is rejected"
assert rejects([{"crate": "a", "bay": "attic", "weight": 5}], DECK), "an unknown bay is rejected"
assert rejects([{"crate": "a", "bay": "core", "weight": 0}], DECK), "a weight of nought is rejected"
print("ok")
