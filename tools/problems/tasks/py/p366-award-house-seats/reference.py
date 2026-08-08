def _whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def award_house_seats(rolls: list, seats: int) -> dict:
    if not isinstance(rolls, list) or not rolls:
        raise ValueError("there must be at least one roll")
    if not _whole(seats) or seats < 1:
        raise ValueError("the seat count must be a whole number above zero")

    read = []
    names = set()
    for roll in rolls:
        if not isinstance(roll, list) or len(roll) != 2:
            raise ValueError("a roll must be a two-element list")
        name, tally = roll
        if not isinstance(name, str) or name == "":
            raise ValueError("a party name must be a non-empty string")
        if name in names:
            raise ValueError("two rolls share a party name")
        names.add(name)
        if not _whole(tally) or tally < 0:
            raise ValueError("a tally must be a whole number that is not negative")
        read.append({"name": name, "tally": tally, "held": 0})

    total = sum(roll["tally"] for roll in read)
    if total == 0:
        raise ValueError("every tally is zero")
    standing = [roll for roll in read if roll["tally"] * 5 >= total]
    if not standing:
        raise ValueError("striking left no roll standing")

    for _ in range(seats):
        best = standing[0]
        for roll in standing[1:]:
            mine = roll["tally"] * (best["held"] + 1)
            theirs = best["tally"] * (roll["held"] + 1)
            if mine > theirs or (mine == theirs and roll["tally"] > best["tally"]):
                best = roll
        best["held"] += 1

    return {roll["name"]: roll["held"] for roll in standing}
