"""Insert a requested slot into a court's booking sheet for the day."""


def reserve_court(booked: list, slot: list, hours: list) -> list:
    for pair in (hours, slot):
        if not isinstance(pair, list) or len(pair) != 2:
            raise ValueError("hours and slot must be two-item lists")
        for bound in pair:
            if isinstance(bound, bool) or not isinstance(bound, int):
                raise ValueError("bounds must be whole minutes")
    open_at, close_at = hours
    if open_at >= close_at:
        raise ValueError("opening must precede closing")
    wanted_from, wanted_until = slot
    if wanted_from >= wanted_until:
        raise ValueError("slot start must precede its end")
    if wanted_from < open_at or wanted_until > close_at:
        raise ValueError("slot must lie inside opening hours")
    if not isinstance(booked, list):
        raise ValueError("booked must be a list")
    sheet = []
    for entry in booked:
        if not isinstance(entry, list) or len(entry) != 2:
            raise ValueError("each booking must be a two-item list")
        for bound in entry:
            if isinstance(bound, bool) or not isinstance(bound, int):
                raise ValueError("booking bounds must be whole minutes")
        if entry[0] >= entry[1]:
            raise ValueError("booking start must precede its end")
        sheet.append([entry[0], entry[1]])
    sheet.sort()
    for earlier, later in zip(sheet, sheet[1:]):
        if earlier[1] > later[0]:
            raise ValueError("existing bookings overlap one another")
    for start, end in sheet:
        if wanted_from < end and start < wanted_until:
            raise ValueError("slot overlaps an existing booking")
    requested = [wanted_from, wanted_until]
    at = len(sheet)
    for index, entry in enumerate(sheet):
        if wanted_until <= entry[0]:
            at = index
            break
    sheet.insert(at, requested)
    return sheet
