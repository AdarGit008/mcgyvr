FARES = {"flex": 0, "saver": 1, "award": 2}


def _whole(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def build_bump_list(travellers: list, seats: int, volunteers: list) -> dict:
    if not isinstance(travellers, list):
        raise ValueError("travellers must be a list")
    if not _whole(seats) or seats < 0:
        raise ValueError("seats must be a whole number of nought or more")
    if not isinstance(volunteers, list):
        raise ValueError("volunteers must be a list")

    codes: set[str] = set()
    stamps: set[int] = set()
    roll: list[tuple[int, int, int, str]] = []
    for traveller in travellers:
        if not isinstance(traveller, dict):
            raise ValueError("a traveller must be a record")
        code = traveller.get("code")
        if not isinstance(code, str) or not code:
            raise ValueError("a code must be a non-empty string")
        if code in codes:
            raise ValueError(f"two travellers carry the code {code}")
        codes.add(code)
        fare = traveller.get("fare")
        if not isinstance(fare, str) or fare not in FARES:
            raise ValueError("fare must be flex, saver or award")
        miles = traveller.get("miles")
        if not _whole(miles) or miles < 0:
            raise ValueError("miles must be a whole number of nought or more")
        checked = traveller.get("checked")
        if not _whole(checked) or checked < 1:
            raise ValueError("checked must be a whole number above nought")
        if checked in stamps:
            raise ValueError(f"two travellers checked in at {checked}")
        stamps.add(checked)
        roll.append((FARES[fare], -miles, checked, code))

    offered: set[str] = set()
    for code in volunteers:
        if not isinstance(code, str) or code not in codes:
            raise ValueError("a volunteer must name a traveller on the roll")
        if code in offered:
            raise ValueError(f"the volunteer {code} is named twice")
        offered.add(code)

    roll.sort()

    owed = max(0, len(roll) - seats)
    bumped: list[str] = []
    gone: set[str] = set()
    for code in volunteers:
        if len(bumped) >= owed:
            break
        bumped.append(code)
        gone.add(code)
    for entry in reversed(roll):
        if len(bumped) >= owed:
            break
        if entry[3] in gone:
            continue
        bumped.append(entry[3])
        gone.add(entry[3])

    boarding = [entry[3] for entry in roll if entry[3] not in gone]
    return {"boarding": boarding, "bumped": bumped}
