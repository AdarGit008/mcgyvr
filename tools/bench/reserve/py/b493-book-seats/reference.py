def seat_row(seat: str) -> str:
    return seat[:1]


def book_seats(seats: list[str]) -> dict[str, list[str]]:
    """Seat codes gathered under their row, in arriving order."""
    rows = {}
    taken = []
    for seat in seats:
        if seat in taken:
            raise ValueError("the seat " + seat + " is already booked")
        taken.append(seat)
        row = seat_row(seat)
        if row not in rows:
            rows[row] = []
        rows[row].append(seat)
    return rows
