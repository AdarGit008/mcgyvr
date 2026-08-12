from solution import seat_block


def rejects(value):
    try:
        seat_block(value)
    except Exception:
        return True
    return False


assert seat_block("12C") == [12, "C"], "a two-digit row"
assert seat_block("1A") == [1, "A"], "a single-digit row"
assert seat_block("100Z") == [100, "Z"], "a three-digit row"
assert rejects("C12"), "the letter cannot lead"
assert rejects("12"), "a row alone is not a seat"
assert rejects(""), "an empty label is rejected"
print("ok")
