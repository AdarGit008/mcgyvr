from solution import normalize_seats

assert normalize_seats(["B12"]) == ["B12"], "a plain seat passes through"
assert normalize_seats(["b-12"]) == ["B12"], "case and hyphen normalize away"
assert normalize_seats([" c007 "]) == ["C7"], "padding and leading zeros strip"
assert normalize_seats(["J4", "A1", "e-9"]) == [
    "J4",
    "A1",
    "E9",
], "input order is kept"
assert normalize_seats([]) == [], "an empty booking stays empty"


def rejects(raw):
    try:
        normalize_seats(raw)
    except ValueError:
        return True
    return False


assert rejects("B7"), "a non-list argument is rejected"
assert rejects([7]), "a non-string entry is rejected"
assert rejects([" "]), "a blank entry is rejected"
assert rejects(["12"]), "a missing row letter is rejected"
assert rejects(["B12x"]), "trailing junk is rejected"
assert rejects(["B000"]), "seat zero is rejected"
assert rejects(["B7", "b-07"]), "a duplicate seat is rejected"
print("ok")
