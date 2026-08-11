from solution import slot_free, free_slots

assert slot_free(1, [2]) is True, "an unbooked slot is free"
assert slot_free(2, [2]) is False, "a booked slot is not"
assert free_slots(3, [2]) == [1, 3], "the booked one is skipped"
assert free_slots(3, []) == [1, 2, 3], "nothing is booked"
assert free_slots(0, []) == [], "there are no slots"
assert free_slots(2, [1, 2]) == [], "everything is booked"
print("ok")
