def first_overload(bookings: list, capacity: int) -> int:
    if isinstance(capacity, bool) or not isinstance(capacity, int) or capacity < 1:
        raise ValueError("capacity must be a positive integer")
    if not isinstance(bookings, list):
        raise ValueError("bookings must be a list of pairs")
    events = []
    for booking in bookings:
        if not isinstance(booking, (list, tuple)) or len(booking) != 2:
            raise ValueError("each booking is a pair of endpoints")
        start, end = booking
        for endpoint in (start, end):
            if isinstance(endpoint, bool) or not isinstance(endpoint, int):
                raise ValueError("booking endpoints must be integers")
        if start >= end:
            raise ValueError("booking start must come strictly before its end")
        events.append((start, 1))
        events.append((end, -1))
    events.sort()
    active = 0
    for time, delta in events:
        active += delta
        if active > capacity:
            return time
    return -1
