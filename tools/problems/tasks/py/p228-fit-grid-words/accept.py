from solution import fit_grid_words

RING = [
    {"id": "a1", "row": 0, "col": 0, "run": "across", "len": 3},
    {"id": "a2", "row": 2, "col": 0, "run": "across", "len": 3},
    {"id": "d1", "row": 0, "col": 0, "run": "down", "len": 3},
    {"id": "d2", "row": 0, "col": 2, "run": "down", "len": 3},
]

CROSS = [
    {"id": "h", "row": 1, "col": 0, "run": "across", "len": 3},
    {"id": "v", "row": 0, "col": 1, "run": "down", "len": 3},
]


def rejects(slots, words):
    try:
        fit_grid_words(slots, words)
    except ValueError:
        return True
    return False


assert fit_grid_words(RING, ["cat", "pit", "no", "cup", "tot"]) == {
    "placed": [
        {"slot": "a1", "word": "cat"},
        {"slot": "a2", "word": "pit"},
        {"slot": "d1", "word": "cup"},
        {"slot": "d2", "word": "tot"},
    ],
    "stuck": "",
}, "the whole ring closes, and the short word is passed over throughout"

assert fit_grid_words(RING, ["dog", "cat", "pit", "cup", "tot"]) == {
    "placed": [{"slot": "a1", "word": "dog"}, {"slot": "a2", "word": "cat"}],
    "stuck": "d1",
}, "an early greedy choice strands a later slot, and nothing is taken back"

assert fit_grid_words(RING, []) == {
    "placed": [],
    "stuck": "a1",
}, "no words at all strands the very first slot"

assert fit_grid_words(CROSS, ["sun", "mad", "cup"]) == {
    "placed": [{"slot": "h", "word": "sun"}, {"slot": "v", "word": "cup"}],
    "stuck": "",
}, "the crossing square rules out the nearer word"

assert fit_grid_words(CROSS, ["sun", "mad"]) == {
    "placed": [{"slot": "h", "word": "sun"}],
    "stuck": "v",
}, "and with nothing else left the crossing slot is stuck"

assert fit_grid_words([{"id": "s", "row": 0, "col": 0, "run": "across", "len": 4}], ["cat", "door"]) == {
    "placed": [{"slot": "s", "word": "door"}],
    "stuck": "",
}, "a word of the wrong length is passed over for a longer one"

assert fit_grid_words(
    [
        {"id": "x", "row": 0, "col": 0, "run": "across", "len": 3},
        {"id": "y", "row": 5, "col": 0, "run": "across", "len": 3},
    ],
    ["cat"],
) == {
    "placed": [{"slot": "x", "word": "cat"}],
    "stuck": "y",
}, "a word once written is not offered again"

assert fit_grid_words(
    [
        {"id": "d", "row": 0, "col": 0, "run": "down", "len": 2},
        {"id": "a", "row": 1, "col": 0, "run": "across", "len": 2},
    ],
    ["ox", "xi"],
) == {
    "placed": [{"slot": "d", "word": "ox"}, {"slot": "a", "word": "xi"}],
    "stuck": "",
}, "a down filling constrains the across slot that meets it"

assert rejects([], ["cat"]), "an empty slot list is rejected"
assert rejects("slots", ["cat"]), "slots that are not a list are rejected"
assert rejects([["a1"]], ["cat"]), "a slot that is not a mapping is rejected"
assert rejects(
    [{"id": "", "row": 0, "col": 0, "run": "across", "len": 3}], ["cat"]
), "an empty id is rejected"
assert rejects(
    [
        {"id": "s", "row": 0, "col": 0, "run": "across", "len": 3},
        {"id": "s", "row": 4, "col": 0, "run": "across", "len": 3},
    ],
    ["cat"],
), "two slots sharing an id are rejected"
assert rejects(
    [{"id": "s", "row": -1, "col": 0, "run": "across", "len": 3}], ["cat"]
), "a negative row is rejected"
assert rejects(
    [{"id": "s", "row": 0, "col": 1.5, "run": "across", "len": 3}], ["cat"]
), "a fractional column is rejected"
assert rejects(
    [{"id": "s", "row": 0, "col": 0, "run": "sideways", "len": 3}], ["cat"]
), "a run that is neither across nor down is rejected"
assert rejects(
    [{"id": "s", "row": 0, "col": 0, "run": "across", "len": 1}], ["cat"]
), "a slot of one square is rejected"
assert rejects(
    [
        {"id": "p", "row": 0, "col": 0, "run": "across", "len": 3},
        {"id": "q", "row": 0, "col": 2, "run": "across", "len": 2},
    ],
    ["cat"],
), "two across slots covering a square in common are rejected"
assert rejects(
    [
        {"id": "p", "row": 0, "col": 0, "run": "down", "len": 3},
        {"id": "q", "row": 2, "col": 0, "run": "down", "len": 2},
    ],
    ["cat"],
), "two down slots covering a square in common are rejected"
assert rejects(RING, "cat"), "words that are not a list are rejected"
assert rejects(RING, ["Cat"]), "a word with a capital is rejected"
assert rejects(RING, [""]), "an empty word is rejected"
assert rejects(RING, ["cat", "cat"]), "a word offered twice is rejected"
assert rejects(RING, [3]), "a word that is not a string is rejected"

print("ok")
