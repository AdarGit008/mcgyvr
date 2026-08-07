from solution import fill_released_seats


def seat(seat_id, holder, band):
    return {"seat": seat_id, "holder": holder, "band": band}


def wait(name, band, years, rank, roving):
    return {
        "name": name,
        "band": band,
        "years": years,
        "rank": rank,
        "roving": roving,
    }


def rejects(seats, waitlist, releases):
    try:
        fill_released_seats(seats, waitlist, releases)
    except ValueError:
        return True
    return False


assert fill_released_seats([], [], []) == [], "no releases, no offers"
assert fill_released_seats([seat("s1", "ada", "gold")], [], ["s1"]) == [
    {"seat": "s1", "taken": None}
], "an empty waitlist leaves the seat standing empty"
assert fill_released_seats(
    [seat("s1", "ada", "gold")],
    [wait("kip", "gold", 5, 3, False), wait("lou", "gold", 5, 2, False)],
    ["s1"],
) == [{"seat": "s1", "taken": "lou"}], (
    "equal years hands the offer to the smaller rank"
)
assert fill_released_seats(
    [seat("s1", "ada", "gold")],
    [
        wait("hal", "silver", 4, 1, False),
        wait("jon", "silver", 8, 3, True),
        wait("ivy", "bronze", 2, 2, True),
    ],
    ["s1"],
) == [{"seat": "s1", "taken": "jon"}], (
    "with no gold runner the offer widens to the roving entries"
)
assert fill_released_seats(
    [seat("s1", "ada", "gold")],
    [wait("meg", "gold", 1, 4, False), wait("nol", "silver", 50, 1, True)],
    ["s1"],
) == [{"seat": "s1", "taken": "meg"}], (
    "a band match beats fifty years of roving standing"
)
assert fill_released_seats(
    [
        seat("s1", "ada", "gold"),
        seat("s2", "ben", "silver"),
        seat("s3", "cyd", "gold"),
    ],
    [
        wait("dot", "gold", 5, 1, False),
        wait("eli", "gold", 9, 2, False),
        wait("fay", "silver", 3, 3, True),
        wait("ben", "gold", 12, 4, False),
        wait("gus", "bronze", 1, 5, True),
    ],
    ["s1", "s2", "s3"],
) == [
    {"seat": "s1", "taken": "eli"},
    {"seat": "s2", "taken": "fay"},
    {"seat": "s3", "taken": "ben"},
], "ben cannot run while seated, and wins the gold seat once he steps out"
assert fill_released_seats(
    [seat("s1", "ada", "gold"), seat("s2", "bea", "silver")],
    [
        wait("mia", "gold", 1, 1, False),
        wait("mia", "silver", 9, 2, False),
        wait("ned", "silver", 3, 3, False),
    ],
    ["s1", "s2"],
) == [
    {"seat": "s1", "taken": "mia"},
    {"seat": "s2", "taken": "ned"},
], "taking a seat strikes every entry in that name, band by band"
assert fill_released_seats(
    [seat("s1", "ada", "gold")],
    [wait("pip", "gold", 2, 1, False), wait("quo", "gold", 1, 2, False)],
    ["s1", "s1"],
) == [
    {"seat": "s1", "taken": "pip"},
    {"seat": "s1", "taken": "quo"},
], "a refilled seat may be released again"

assert rejects("s", [], []), "the seats are a list"
assert rejects([seat("s1", "ada", "gold")], [], "s1"), "the releases are a list"
assert rejects([seat("s1", "ada", "gold"), seat("s1", "bea", "gold")], [], []), (
    "two seats may not share an id"
)
assert rejects([seat("s1", "ada", "gold"), seat("s2", "ada", "gold")], [], []), (
    "one name may not hold two seats"
)
assert rejects([], [wait("kit", "gold", -1, 1, False)], []), (
    "years is never negative"
)
assert rejects([], [wait("kit", "gold", 2, 1.5, False)], []), (
    "rank is a whole number"
)
assert rejects([], [wait("kit", "gold", 2, 1, "no")], []), "roving is a boolean"
assert rejects(
    [], [wait("kit", "gold", 2, 1, False), wait("lyn", "silver", 3, 1, False)], []
), "two entries may not share a rank"
assert rejects(
    [], [wait("kit", "gold", 2, 1, False), wait("kit", "gold", 3, 2, False)], []
), "one name waits on a band only once"
assert rejects([seat("s1", "ada", "gold")], [], ["s9"]), (
    "a release must name a seat"
)
assert rejects([seat("s1", "ada", "gold")], [], ["s1", "s1"]), (
    "an empty seat cannot be released twice"
)
print("ok")
