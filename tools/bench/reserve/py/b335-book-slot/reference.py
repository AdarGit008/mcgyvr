def slot_free(slot: int, booked: list) -> bool:
    return slot not in booked


def free_slots(last: int, booked: list) -> list:
    return [slot for slot in range(1, last + 1) if slot_free(slot, booked)]
