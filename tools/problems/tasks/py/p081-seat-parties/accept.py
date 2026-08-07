from solution import seat_parties

assert seat_parties([4, 6], []) == [], "no parties, no records"

assert seat_parties([4, 6], [2, 2]) == ["1-1", "1-3"], (
    "seats advance within a row"
)

assert seat_parties([4, 6], [3, 2, 1]) == ["1-1", "2-1", "1-4"], (
    "a party too wide for row one spills to row two"
)

assert seat_parties([3, 3], [3, 3, 1]) == ["1-1", "2-1", "rejected:full"], (
    "a filled hall rejects with full"
)

assert seat_parties([3, 5], [6]) == ["rejected:too_big"], (
    "a party longer than the longest row is too_big"
)

assert seat_parties([3, 3], [3, 3, 3, 4]) == [
    "1-1",
    "2-1",
    "rejected:full",
    "rejected:too_big",
], "full and too_big are distinguished"

assert seat_parties([3], [2, 2, 1]) == ["1-1", "rejected:full", "1-3"], (
    "a rejected party occupies nothing and later parties still seat"
)


def rejects(rows, parties):
    try:
        seat_parties(rows, parties)
    except ValueError:
        return True
    return False


assert rejects([3], [0]), "size zero is an error"

print("ok")
