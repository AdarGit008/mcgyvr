def slot_pack(items: list, capacity: int) -> list:
    slots = []
    for i in range(0, len(items), capacity):
        slots.append(items[i : i + capacity])
    return slots
