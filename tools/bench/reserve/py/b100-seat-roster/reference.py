import re


def normalize_seats(raw: list) -> list:
    if not isinstance(raw, list):
        raise ValueError("normalize_seats expects a list")
    seats = []
    seen = set()
    for entry in raw:
        if not isinstance(entry, str):
            raise ValueError("seat entries must be strings")
        if not entry.strip():
            raise ValueError("blank seat entry")
        match = re.fullmatch(r"\s*([A-Za-z])-?(\d{1,3})\s*", entry)
        if match is None:
            raise ValueError("malformed seat: " + entry)
        number = int(match.group(2))
        if number == 0:
            raise ValueError("seat numbers start at 1")
        seat = match.group(1).upper() + str(number)
        if seat in seen:
            raise ValueError("duplicate seat: " + seat)
        seen.add(seat)
        seats.append(seat)
    return seats
