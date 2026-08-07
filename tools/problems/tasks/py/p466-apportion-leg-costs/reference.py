def _whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def apportion_leg_costs(legs: list, travellers: list) -> list:
    if not isinstance(legs, list) or not isinstance(travellers, list):
        raise ValueError("apportion_leg_costs expects two lists")
    if not legs:
        raise ValueError("the trip has no legs")
    if not travellers:
        raise ValueError("the trip has no travellers")

    order = {}
    cost = []
    payer = []
    for leg in legs:
        if not isinstance(leg, dict):
            raise ValueError("a leg is not a mapping")
        if sorted(leg) != ["cents", "name", "payer"]:
            raise ValueError("a leg carries exactly name, cents and payer")
        name = leg["name"]
        if not isinstance(name, str) or not name:
            raise ValueError("a leg name is not a non-empty string")
        if name in order:
            raise ValueError("two legs share a name")
        cents = leg["cents"]
        if not _whole(cents) or cents < 0:
            raise ValueError("a leg's cents are not whole or fall below nought")
        paid_by = leg["payer"]
        if not isinstance(paid_by, str) or not paid_by:
            raise ValueError("a leg's payer is not a non-empty string")
        order[name] = len(cost)
        cost.append(cents)
        payer.append(paid_by)

    joined = {}
    for rider in travellers:
        if not isinstance(rider, dict):
            raise ValueError("a traveller is not a mapping")
        if sorted(rider) != ["joins", "leaves", "name"]:
            raise ValueError("a traveller carries exactly name, joins and leaves")
        name = rider["name"]
        if not isinstance(name, str) or not name:
            raise ValueError("a traveller name is not a non-empty string")
        if name in joined:
            raise ValueError("two travellers share a name")
        joins = rider["joins"]
        leaves = rider["leaves"]
        if not isinstance(joins, str) or joins not in order:
            raise ValueError("a traveller joins at a leg the trip does not run")
        if not isinstance(leaves, str) or leaves not in order:
            raise ValueError("a traveller leaves at a leg the trip does not run")
        if order[leaves] < order[joins]:
            raise ValueError("a traveller leaves before joining")
        joined[name] = (order[joins], order[leaves])

    for who in payer:
        if who not in joined:
            raise ValueError("a leg is paid by someone not on the trip")

    names = sorted(joined)
    owes = {name: 0 for name in names}
    handed = {name: 0 for name in names}

    for index, cents in enumerate(cost):
        present = [
            name for name in names if joined[name][0] <= index <= joined[name][1]
        ]
        if not present:
            raise ValueError("a leg carries nobody at all")
        each = cents // len(present)
        spare = cents - each * len(present)
        for name in present:
            extra = 1 if spare > 0 else 0
            spare -= extra
            owes[name] += each + extra
        handed[payer[index]] += cents

    return [
        {"name": name, "owes": owes[name], "paid": handed[name]} for name in names
    ]
