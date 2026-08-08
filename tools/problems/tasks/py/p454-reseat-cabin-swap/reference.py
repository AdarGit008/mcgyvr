import re

SEAT = re.compile(r"^([1-9][0-9]*)([A-Z])$")
WANTS = ("window", "aisle", "any")


def _whole(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _capitals(value) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[A-Z]+", value) is not None


def reseat_cabin(holders: list, cabin: dict) -> dict:
    if not isinstance(holders, list):
        raise ValueError("holders must be a list")
    if not isinstance(cabin, dict):
        raise ValueError("cabin must be a record")
    if not _whole(cabin.get("rows")) or cabin["rows"] < 1:
        raise ValueError("rows must be a whole number above nought")
    if not _capitals(cabin.get("left")) or not _capitals(cabin.get("right")):
        raise ValueError("left and right must be non-empty runs of capital letters")
    order = cabin["left"] + cabin["right"]
    if len(set(order)) != len(order):
        raise ValueError("a seat letter is used twice in one row")
    if not isinstance(cabin.get("blocked"), list):
        raise ValueError("blocked must be a list")

    def rank(row: int, letter: str) -> int:
        return (row - 1) * len(order) + order.index(letter)

    windows = {cabin["left"][0], cabin["right"][-1]}
    aisles = {cabin["left"][-1], cabin["right"][0]}

    free: dict[int, str] = {}
    for row in range(1, cabin["rows"] + 1):
        for letter in order:
            free[rank(row, letter)] = f"{row}{letter}"
    for label in cabin["blocked"]:
        parsed = SEAT.match(label) if isinstance(label, str) else None
        if parsed is None:
            raise ValueError("a blocked seat must be a row number then one capital letter")
        row = int(parsed.group(1))
        if row > cabin["rows"] or parsed.group(2) not in order:
            raise ValueError(f"the cabin has no seat {label}")
        free.pop(rank(row, parsed.group(2)), None)

    names: set[str] = set()
    old_seats: set[str] = set()
    queue: list[tuple[int, str, str, str]] = []
    for holder in holders:
        if not isinstance(holder, dict):
            raise ValueError("a holder must be a record")
        name = holder.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError("a name must be a non-empty string")
        if name in names:
            raise ValueError(f"two holders answer to the name {name}")
        names.add(name)
        seat = holder.get("seat")
        parsed = SEAT.match(seat) if isinstance(seat, str) else None
        if parsed is None:
            raise ValueError("a seat must be a row number then one capital letter")
        if seat in old_seats:
            raise ValueError(f"two holders claim the old seat {seat}")
        old_seats.add(seat)
        if holder.get("want") not in WANTS:
            raise ValueError("want must be window, aisle or any")
        queue.append((int(parsed.group(1)), parsed.group(2), name, holder["want"]))

    queue.sort(key=lambda rider: (rider[0], rider[1]))

    def suits(want: str, letter: str) -> bool:
        if want == "any":
            return True
        if want == "window":
            return letter in windows
        return letter in aisles

    seated: list[str] = []
    bumped: list[str] = []
    for row, letter, name, want in queue:
        keys = sorted(free)
        held = rank(row, letter) if row <= cabin["rows"] and letter in order else -1
        if held >= 0 and held in free:
            seated.append(f"{name} {free[held]} kept")
            del free[held]
            continue
        chosen = -1
        for key in keys:
            if suits(want, free[key][-1]):
                chosen = key
                break
        if chosen >= 0:
            seated.append(f"{name} {free[chosen]} moved")
            del free[chosen]
            continue
        if keys:
            seated.append(f"{name} {free[keys[0]]} shifted")
            del free[keys[0]]
            continue
        bumped.append(name)
    return {"seated": seated, "bumped": bumped}
