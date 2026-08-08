from solution import band_parcel_charge

BOOK = {
    "zones": ["home", "near", "far"],
    "steps": [
        {"upTo": 500, "cents": [299, 399, 599]},
        {"upTo": 2000, "cents": [499, 699, 999]},
        {"upTo": None, "cents": [899, 1299, 1899]},
    ],
    "extras": [
        {"mark": "fragile", "cents": 150, "zones": None},
        {"mark": "rush", "cents": 250, "zones": ["near", "far"]},
    ],
    "round": 5,
}

PLAIN = {"zones": ["z"], "steps": [{"upTo": None, "cents": [100]}], "extras": [], "round": 5}
PARCEL = {"zone": "z", "grams": 10, "marks": []}


def bent(patch):
    book = dict(PLAIN)
    book.update(patch)
    return book


def parcel(patch):
    one = dict(PARCEL)
    one.update(patch)
    return one


def rejects(book, one):
    try:
        band_parcel_charge(book, one)
    except ValueError:
        return True
    return False


assert band_parcel_charge(BOOK, {"zone": "home", "grams": 500, "marks": []}) == {
    "band": 0,
    "base": 299,
    "extra": 0,
    "total": 300,
    "applied": [],
}, "a parcel sitting exactly on a band's weight stays in that band"

assert band_parcel_charge(BOOK, {"zone": "home", "grams": 501, "marks": []}) == {
    "band": 1,
    "base": 499,
    "extra": 0,
    "total": 500,
    "applied": [],
}, "one gram past the edge moves it up a band"

assert band_parcel_charge(
    BOOK, {"zone": "far", "grams": 5000, "marks": ["rush", "fragile"]}
) == {
    "band": 2,
    "base": 1899,
    "extra": 400,
    "total": 2300,
    "applied": ["fragile", "rush"],
}, "the open band catches the heavy parcel, and the charges follow the book's order"

assert band_parcel_charge(BOOK, {"zone": "home", "grams": 100, "marks": ["rush"]}) == {
    "band": 0,
    "base": 299,
    "extra": 0,
    "total": 300,
    "applied": [],
}, "a charge that does not cover the zone is not made"

assert band_parcel_charge(BOOK, {"zone": "near", "grams": 2000, "marks": ["fragile"]}) == {
    "band": 1,
    "base": 699,
    "extra": 150,
    "total": 850,
    "applied": ["fragile"],
}, "the middle band with one charge on top"

assert band_parcel_charge(BOOK, {"zone": "near", "grams": 2001, "marks": []}) == {
    "band": 2,
    "base": 1299,
    "extra": 0,
    "total": 1300,
    "applied": [],
}, "the price is read from the parcel's own zone column"

assert band_parcel_charge(PLAIN, PARCEL) == {
    "band": 0,
    "base": 100,
    "extra": 0,
    "total": 100,
    "applied": [],
}, "a sum already sitting on a multiple is left alone"

assert band_parcel_charge(
    dict(BOOK, round=1), {"zone": "home", "grams": 1, "marks": ["fragile"]}
) == {
    "band": 0,
    "base": 299,
    "extra": 150,
    "total": 449,
    "applied": ["fragile"],
}, "rounding to one cent changes nothing"

assert band_parcel_charge(dict(BOOK, round=100), {"zone": "far", "grams": 1, "marks": []}) == {
    "band": 0,
    "base": 599,
    "extra": 0,
    "total": 600,
    "applied": [],
}, "a coarse rounding step lifts the sum a long way"

assert rejects([], PARCEL), "a book that is not a mapping is rejected"
assert rejects(PLAIN, "z"), "a parcel that is not a mapping is rejected"
assert rejects(bent({"zones": []}), PARCEL), "an empty zone list is rejected"
assert rejects(bent({"zones": ["z", "z"]}), PARCEL), "a zone listed twice is rejected"
assert rejects(bent({"zones": [""]}), PARCEL), "an empty zone name is rejected"
assert rejects(bent({"steps": []}), PARCEL), "a book with no bands is rejected"
assert rejects(bent({"steps": ["x"]}), PARCEL), "a band that is not a mapping is rejected"
assert rejects(
    bent({"steps": [{"upTo": "500", "cents": [1]}, {"upTo": None, "cents": [2]}]}), PARCEL
), "a stated weight that is not a number is rejected"
assert rejects(
    bent({"steps": [{"upTo": 0, "cents": [1]}, {"upTo": None, "cents": [2]}]}), PARCEL
), "a stated weight of zero is rejected"
assert rejects(
    bent(
        {
            "steps": [
                {"upTo": 500, "cents": [1]},
                {"upTo": 500, "cents": [2]},
                {"upTo": None, "cents": [3]},
            ]
        }
    ),
    PARCEL,
), "stated weights that do not climb are rejected"
assert rejects(
    bent({"steps": [{"upTo": None, "cents": [1]}, {"upTo": 500, "cents": [2]}]}), PARCEL
), "an open band that is not last is rejected"
assert rejects(
    bent({"steps": [{"upTo": 500, "cents": [1]}]}), PARCEL
), "a book with no open band is rejected"
assert rejects(
    bent({"steps": [{"upTo": None, "cents": [1, 2]}]}), PARCEL
), "a price list longer than the zone list is rejected"
assert rejects(
    bent({"steps": [{"upTo": None, "cents": [-1]}]}), PARCEL
), "a negative price is rejected"
assert rejects(bent({"extras": "x"}), PARCEL), "extras that are not a list are rejected"
assert rejects(
    bent(
        {
            "extras": [
                {"mark": "m", "cents": 1, "zones": None},
                {"mark": "m", "cents": 2, "zones": None},
            ]
        }
    ),
    PARCEL,
), "a mark charged twice is rejected"
assert rejects(
    bent({"extras": [{"mark": "m", "cents": 1, "zones": ["nowhere"]}]}), PARCEL
), "a charge naming an unknown zone is rejected"
assert rejects(
    bent({"extras": [{"mark": "m", "cents": -5, "zones": None}]}), PARCEL
), "a negative charge is rejected"
assert rejects(bent({"round": 0}), PARCEL), "a rounding step of zero is rejected"
assert rejects(PLAIN, parcel({"zone": "q"})), "an unknown parcel zone is rejected"
assert rejects(PLAIN, parcel({"grams": 0})), "grams of zero are rejected"
assert rejects(PLAIN, parcel({"grams": 1.5})), "fractional grams are rejected"
assert rejects(PLAIN, parcel({"marks": "m"})), "marks that are not a list are rejected"
assert rejects(PLAIN, parcel({"marks": ["nope"]})), "a mark the book never names is rejected"
assert rejects(
    bent({"extras": [{"mark": "m", "cents": 1, "zones": None}]}), parcel({"marks": ["m", "m"]})
), "a mark carried twice is rejected"

print("ok")
