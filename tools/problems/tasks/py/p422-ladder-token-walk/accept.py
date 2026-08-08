from solution import walk_ladder_board


def rejects(*args):
    try:
        walk_ladder_board(*args)
    except ValueError:
        return True
    return False


assert walk_ladder_board(10, [], [8, 3]) == 9, "a push past the end is forfeit"
assert walk_ladder_board(10, [], [7, 4, 2]) == 10, "a forfeit does not end the walk"
assert walk_ladder_board(12, [[4, 9]], [3]) == 9, "a mouth carries the counter ahead"
assert walk_ladder_board(12, [[10, 2]], [9]) == 2, "an exit may sit behind its mouth"
assert walk_ladder_board(5, [[3, 5]], []) == 1, "no pushes leaves the counter at the start"
assert walk_ladder_board(8, [[4, 8]], [3, 2]) == 8, "a carry onto the last square finishes"
assert (
    walk_ladder_board(20, [[3, 11], [16, 6], [8, 2]], [2, 5, 2, 3, 16, 15, 4]) == 20
), "a long track with three chutes"
assert (
    walk_ladder_board(20, [[3, 11], [16, 6], [8, 2]], [2, 5, 2, 3]) == 5
), "the same track stopped before the finish"
assert walk_ladder_board(2, [], [1]) == 2, "the shortest legal track"

assert rejects(1, [], [1]), "a size under 2 is refused"
assert rejects(5.5, [], [1]), "a fractional size is refused"
assert rejects(9, [[3, 3]], [1]), "a mouth may not be its own exit"
assert rejects(6, [[1, 4]], [1]), "a mouth on square 1 is refused"
assert rejects(6, [[6, 2]], [1]), "a mouth on the last square is refused"
assert rejects(8, [[3, 5], [3, 6]], [1]), "two chutes sharing a mouth are refused"
assert rejects(9, [[3, 5], [5, 7]], [1]), "an exit that is a mouth is refused"
assert rejects(9, [[3, 12]], [1]), "a square off the track is refused"
assert rejects(9, [[3]], [1]), "a chute that is not a pair is refused"
assert rejects(9, [], [0]), "a push of zero is refused"
assert rejects(9, [], [2.5]), "a fractional push is refused"
print("ok")
