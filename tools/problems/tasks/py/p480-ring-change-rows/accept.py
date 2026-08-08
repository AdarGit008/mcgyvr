from solution import ring_change_rows

assert ring_change_rows(4, [[], [1, 4]], 9) == [
    [1, 2, 3, 4],
    [2, 1, 4, 3],
    [2, 4, 1, 3],
    [4, 2, 3, 1],
    [4, 3, 2, 1],
    [3, 4, 1, 2],
    [3, 1, 4, 2],
    [1, 3, 2, 4],
    [1, 2, 3, 4],
], "two changes taken in turn bring four bells back to rounds"

assert ring_change_rows(4, [[], [1, 4]], 1) == [
    [1, 2, 3, 4]
], "a count of one gives back rounds alone"

assert ring_change_rows(2, [[]], 3) == [
    [1, 2],
    [2, 1],
    [1, 2],
], "two bells swap and swap back"

assert ring_change_rows(6, [[1, 6]], 2) == [
    [1, 2, 3, 4, 5, 6],
    [1, 3, 2, 5, 4, 6],
], "the four bells between two standing places pair off from the left"

assert ring_change_rows(4, [[1, 2], [3, 4]], 4) == [
    [1, 2, 3, 4],
    [1, 2, 4, 3],
    [2, 1, 4, 3],
    [2, 1, 3, 4],
], "changes are taken up again from the first once the last is rung"

assert ring_change_rows(3, [[3]], 3) == [
    [1, 2, 3],
    [2, 1, 3],
    [1, 2, 3],
], "a standing place at the back leaves the front pair to swap"

assert ring_change_rows(4, [[]], 3) == [
    [1, 2, 3, 4],
    [2, 1, 4, 3],
    [1, 2, 3, 4],
], "a change with nothing standing swaps every pair"


def rejects(bells, changes, count):
    try:
        ring_change_rows(bells, changes, count)
    except ValueError:
        return True
    return False


assert rejects(1, [[]], 2), "fewer than two bells is rejected"
assert rejects(13, [[]], 2), "more than twelve bells is rejected"
assert rejects(2.5, [[]], 2), "a bells argument that is not whole is rejected"
assert rejects(4, "14", 2), "a changes argument that is not a list is rejected"
assert rejects(4, [], 2), "an empty changes argument is rejected"
assert rejects(4, ["14"], 2), "a change that is not a list is rejected"
assert rejects(4, [[0]], 2), "a place below one is rejected"
assert rejects(4, [[5]], 2), "a place past the last bell is rejected"
assert rejects(4, [[2, 1]], 2), "places that do not climb are rejected"
assert rejects(4, [[1, 1]], 2), "a place written twice is rejected"
assert rejects(4, [[2]], 2), "a change leaving an odd run of movers is rejected"
assert rejects(3, [[]], 2), "an odd peal with nothing standing is rejected"
assert rejects(4, [[]], 0), "a count below one is rejected"
print("ok")
