def overlap_any(bookings: list) -> bool:
    for i in range(len(bookings)):
        for j in range(i + 1, len(bookings)):
            if bookings[i][0] < bookings[j][1] and bookings[j][0] < bookings[i][1]:
                return True
    return False
