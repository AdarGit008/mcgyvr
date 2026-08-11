from solution import book_seats


def rejects(seats):
    try:
        book_seats(seats)
    except Exception:
        return True
    return False


assert book_seats(["a1", "a2", "b1"]) == {"a": ["a1", "a2"], "b": ["b1"]}, "seats gather under their row"
assert book_seats(["b2", "a1"]) == {"b": ["b2"], "a": ["a1"]}, "rows appear as they arrive"
assert book_seats(["a3"]) == {"a": ["a3"]}, "a single seat"
assert book_seats(["a2", "a1"]) == {"a": ["a2", "a1"]}, "seats hold their arriving order"
assert book_seats([]) == {}, "no seats at all"
assert rejects(["a1", "a1"]), "a seat booked twice is rejected"
print("ok")
