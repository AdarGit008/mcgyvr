from solution import check_band_drift

assert check_band_drift(
    [
        {"code": "L1", "hits": 500, "was": "A"},
        {"code": "L2", "hits": 300, "was": "C"},
        {"code": "L3", "hits": 150, "was": "A"},
        {"code": "L4", "hits": 50, "was": "C"},
    ],
    [700, 950],
) == {"up": ["L2"], "down": ["L3"], "steady": 2}, "one nearer, one further, two unmoved"

assert check_band_drift(
    [
        {"code": "P", "hits": 60, "was": "B"},
        {"code": "Q", "hits": 30, "was": "B"},
        {"code": "R", "hits": 10, "was": "A"},
        {"code": "Z", "hits": 0, "was": "C"},
    ],
    [600, 900],
) == {"up": ["P"], "down": ["R"], "steady": 2}, "a code with no hits rides on the last class"

assert check_band_drift(
    [{"code": "B", "hits": 100, "was": "B"}, {"code": "A", "hits": 100, "was": "A"}],
    [500, 900],
) == {
    "up": [],
    "down": ["B"],
    "steady": 1,
}, "a tie of hits is swept by code, and the pile is weighed after the entry"

assert check_band_drift([{"code": "S", "hits": 10, "was": "A"}], [1, 999]) == {
    "up": [],
    "down": ["S"],
    "steady": 0,
}, "a lone code can outrun both marks"

assert check_band_drift(
    [
        {"code": "M", "hits": 6, "was": "A"},
        {"code": "N", "hits": 3, "was": "C"},
        {"code": "O", "hits": 1, "was": "B"},
    ],
    [600, 900],
) == {"up": ["N"], "down": ["O"], "steady": 1}, "landing exactly on a mark keeps the nearer class"

sound = [{"code": "G", "hits": 4, "was": "A"}, {"code": "H", "hits": 1, "was": "C"}]


def rejects(entries, marks):
    try:
        check_band_drift(entries, marks)
    except ValueError:
        return True
    return False


assert rejects("x", [500, 900]), "entries that are not a list"
assert rejects([], [500, 900]), "no entries at all"
assert rejects([3], [500, 900]), "an entry that is not a record"
assert rejects([{"code": "", "hits": 1, "was": "A"}], [500, 900]), "an empty code"
assert rejects(
    [{"code": "G", "hits": 1, "was": "A"}, {"code": "G", "hits": 2, "was": "B"}], [500, 900]
), "one code twice"
assert rejects([{"code": "G", "hits": -1, "was": "A"}], [500, 900]), "hits below nothing"
assert rejects([{"code": "G", "hits": 1.5, "was": "A"}], [500, 900]), "fractional hits"
assert rejects([{"code": "G", "hits": 1, "was": "D"}], [500, 900]), "a class outside the three"
assert rejects([{"code": "G", "hits": 0, "was": "A"}], [500, 900]), "a season with no hits"
assert rejects(sound, [500]), "only one mark"
assert rejects(sound, [0, 900]), "a mark below one"
assert rejects(sound, [500, 1000]), "a mark above nine hundred and ninety-nine"
assert rejects(sound, [900, 500]), "marks the wrong way round"
print("ok")
