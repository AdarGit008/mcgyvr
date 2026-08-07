import re

SEAT = re.compile(r"(\d+)([A-Z])")


def _is_count(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def order_boarding_bands(layout: str, rows: int, band: int, passengers: list) -> list:
    if not isinstance(layout, str):
        raise ValueError("the layout is a string")
    sides = layout.split("|")
    if len(sides) != 2:
        raise ValueError("the layout carries exactly one aisle bar")
    if sides[0] == "" or sides[1] == "":
        raise ValueError("both sides of the aisle carry seats")
    letters = sides[0] + sides[1]
    place: dict = {}
    for index, letter in enumerate(letters):
        if letter < "A" or letter > "Z":
            raise ValueError("a seat letter is a capital letter")
        if letter in place:
            raise ValueError(f"the layout writes {letter} twice")
        place[letter] = index
    if not _is_count(rows) or not _is_count(band):
        raise ValueError("rows and the band size are whole numbers of one or more")
    if not isinstance(passengers, list):
        raise ValueError("the passenger list is a list")

    windows = {sides[0][0], sides[1][-1]}
    aisles = {sides[0][-1], sides[1][0]}
    names: set = set()
    seats: set = set()
    called: list = []
    for entry in passengers:
        if not isinstance(entry, list) or len(entry) != 2:
            raise ValueError("a passenger is a pair of a name and a seat")
        name, seat = entry
        if not isinstance(name, str) or name == "":
            raise ValueError("a name is a non-empty string")
        if name in names:
            raise ValueError(f"two passengers answer to {name}")
        names.add(name)
        if not isinstance(seat, str):
            raise ValueError("a seat is a string")
        parsed = SEAT.fullmatch(seat)
        if parsed is None:
            raise ValueError("a seat is digits followed by one letter")
        row = int(parsed.group(1))
        letter = parsed.group(2)
        if row < 1 or row > rows:
            raise ValueError(f"row {row} is not in this cabin")
        if letter not in place:
            raise ValueError(f"the layout has no seat {letter}")
        key = f"{row}{letter}"
        if key in seats:
            raise ValueError(f"two passengers hold seat {key}")
        seats.add(key)
        klass = 0 if letter in windows else 2 if letter in aisles else 1
        called.append(((rows - row) // band + 1, klass, -row, place[letter], name))

    called.sort()
    return [one[4] for one in called]
