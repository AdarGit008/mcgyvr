from solution import cheapest_packs

assert cheapest_packs(6, [[3, 2]]) == 4, "one pack size bought twice"
assert cheapest_packs(6, [[4, 3], [3, 2]]) == 4, "two small packs beat the big pack"
assert cheapest_packs(10, [[4, 4], [3, 2]]) == 8, "mixed pack sizes fill exactly"
assert cheapest_packs(0, [[5, 3]]) == 0, "an order of zero costs nothing"
assert cheapest_packs(7, [[7, 9], [3, 2], [4, 3]]) == 5, "a combination undercuts the exact pack"
assert cheapest_packs(5, [[2, 1]]) == -1, "an unfillable order yields -1"
assert cheapest_packs(9, [[3, 0]]) == 0, "free packs cost nothing"


def rejects(*args):
    try:
        cheapest_packs(*args)
    except Exception:
        return True
    return False


assert rejects(-1, [[2, 1]]), "negative order is rejected"
assert rejects(2.5, [[2, 1]]), "fractional order is rejected"
assert rejects(4, []), "empty pack list is rejected"
assert rejects(4, [[0, 1]]), "zero pack size is rejected"
assert rejects(4, [[2, -1]]), "negative pack price is rejected"
print("ok")
