"""Which appointment bookings collide with one another."""


def clash_pairs(bookings: list) -> list:
    if not isinstance(bookings, list):
        raise ValueError("clash_pairs expects a list of bookings")
    for booking in bookings:
        if not isinstance(booking, list) or len(booking) != 2:
            raise ValueError("a booking must be a [start, end] pair")
        start, end = booking
        for bound in (start, end):
            if isinstance(bound, bool) or not isinstance(bound, int):
                raise ValueError("booking bounds must be integers")
        if start >= end:
            raise ValueError("booking start must precede its end")
    pairs = []
    for i in range(len(bookings)):
        for j in range(i + 1, len(bookings)):
            if bookings[i][0] < bookings[j][1] and bookings[j][0] < bookings[i][1]:
                pairs.append([i, j])
    return pairs
