from solution import audit_artist_gaps


def rejects(playlist, spacing):
    try:
        audit_artist_gaps(playlist, spacing)
    except ValueError:
        return True
    return False


assert audit_artist_gaps(["Vela", "Kesh", "Vela", "Orn", "Pell", "Kesh"], 2) == [
    {"artist": "Vela", "at": 2, "between": 1}
], "one track between two plays is short of two"
assert (
    audit_artist_gaps(["Vela", "Kesh", "Vela", "Orn", "Pell", "Kesh"], 1) == []
), "one track between is enough for a spacing of one"
assert audit_artist_gaps(["Vela", "Vela"], 0) == [], "a spacing of zero can never be broken"
assert audit_artist_gaps(["Vela", "Vela"], 1) == [
    {"artist": "Vela", "at": 1, "between": 0}
], "back to back plays sit no tracks apart"
assert audit_artist_gaps(["Orn", "Orn", "Orn"], 1) == [
    {"artist": "Orn", "at": 1, "between": 0},
    {"artist": "Orn", "at": 2, "between": 0},
], "three in a row give two broken pairs"
assert audit_artist_gaps(["Vela", "x", "Vela", "y", "Vela"], 4) == [
    {"artist": "Vela", "at": 2, "between": 1},
    {"artist": "Vela", "at": 4, "between": 1},
], "the first and last plays are not compared across the middle one"
assert (
    audit_artist_gaps(["Vela", "Kesh", "Orn"], 5) == []
), "an artist played once is never crowded"
assert audit_artist_gaps(["Vela", "Kesh", "Kesh", "Vela"], 3) == [
    {"artist": "Kesh", "at": 2, "between": 0},
    {"artist": "Vela", "at": 3, "between": 2},
], "the report is ordered by position, not by artist"

assert rejects([], 1), "an empty playlist is refused"
assert rejects("Vela", 1), "a playlist that is not a list is refused"
assert rejects(["Vela", ""], 1), "an empty artist name is refused"
assert rejects(["Vela", 7], 1), "an entry that is not a string is refused"
assert rejects(["Vela"], -1), "a negative spacing is refused"
assert rejects(["Vela"], 1.5), "a spacing that is not whole is refused"
assert rejects(["Vela"], "two"), "a spacing that is not a number is refused"
print("ok")
