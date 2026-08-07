from solution import fold_parcels


def ev(kind, parcel):
    return {"type": kind, "parcel": parcel}


assert fold_parcels([]) == {}, "no events, empty depot"

assert fold_parcels(
    [
        ev("accept", "p1"),
        ev("accept", "p2"),
        ev("load", "p1"),
        ev("deliver", "p1"),
        ev("load", "p2"),
    ]
) == {"p1": "delivered", "p2": "in_transit"}, (
    "independent parcels fold independently"
)

assert fold_parcels(
    [ev("accept", "a"), ev("load", "a"), ev("deliver", "a"), ev("bounce", "a")]
) == {"a": "returned"}, "full lifecycle to returned"

assert fold_parcels([ev("accept", "a"), ev("lose", "a")]) == {"a": "lost"}, (
    "an accepted parcel can be lost"
)

assert fold_parcels(
    [ev("accept", "a"), ev("load", "a"), ev("lose", "a")]
) == {"a": "lost"}, "a parcel in transit can be lost"


def rejects_naming(events, index):
    try:
        fold_parcels(events)
    except ValueError as error:
        return str(index) in str(error)
    return False


assert rejects_naming([ev("accept", "a"), ev("accept", "a")], 1), (
    "re-accepting names the event index"
)
assert rejects_naming([ev("load", "ghost")], 0), (
    "an event for a parcel never accepted is an error"
)
assert rejects_naming([ev("accept", "a"), ev("deliver", "a")], 1), (
    "deliver straight from accepted is an invalid transition"
)
assert rejects_naming(
    [
        ev("accept", "a"),
        ev("load", "a"),
        ev("deliver", "a"),
        ev("bounce", "a"),
        ev("load", "a"),
    ],
    4,
), "a returned parcel admits nothing further"
assert rejects_naming([ev("accept", "a"), ev("lose", "a"), ev("load", "a")], 2), (
    "a lost parcel admits nothing further"
)
assert rejects_naming([ev("accept", "a"), ev("teleport", "a")], 1), (
    "an unknown type is an error naming its index"
)

print("ok")
