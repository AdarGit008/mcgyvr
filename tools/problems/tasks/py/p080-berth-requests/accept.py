from solution import assign_berths


def dock(boat, owner, size):
    return {"op": "dock", "boat": boat, "owner": owner, "size": size}


def leave(boat):
    return {"op": "leave", "boat": boat}


TWO_BERTHS = [{"id": "B1", "size": 10}, {"id": "B2", "size": 4}]

assert assign_berths(TWO_BERTHS, {}, [dock("Swan", "ann", 3)]) == ["B1"], (
    "first fit takes the first big-enough berth, not the snuggest"
)

assert assign_berths(
    TWO_BERTHS,
    {},
    [dock("Swan", "ann", 8), dock("Gull", "ann", 3), dock("Tern", "ann", 5)],
) == ["B1", "B2", "rejected:no_berth"], (
    "an occupied berth is skipped and an oversize boat is refused"
)

assert assign_berths(
    TWO_BERTHS,
    {"ann": 1},
    [
        dock("Swan", "ann", 3),
        dock("Gull", "ann", 3),
        leave("Swan"),
        dock("Gull", "ann", 3),
    ],
) == ["B1", "rejected:over_quota", "left", "B1"], (
    "leaving releases both the berth and the owner's quota"
)

assert assign_berths(
    TWO_BERTHS, {"ann": 1}, [dock("Swan", "ann", 3), dock("Swan", "ann", 3)]
) == ["B1", "rejected:already_docked"], "already_docked outranks over_quota"

assert assign_berths(TWO_BERTHS, {}, [leave("Ghost")]) == [
    "rejected:not_docked"
], "leaving while not docked is refused"

assert assign_berths(TWO_BERTHS, {"bob": 0}, [dock("Skua", "bob", 1)]) == [
    "rejected:over_quota"
], "a zero quota holds nothing"


def rejects(berths, quota, requests):
    try:
        assign_berths(berths, quota, requests)
    except ValueError:
        return True
    return False


assert rejects(TWO_BERTHS, {}, [{"op": "paint", "boat": "Swan"}]), (
    "an unknown op is an error"
)

assert rejects(
    [{"id": "B1", "size": 5}, {"id": "B1", "size": 6}], {}, []
), "duplicate berth ids are an error"

print("ok")
