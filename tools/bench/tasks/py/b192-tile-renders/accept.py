from solution import tile_renders

assert tile_renders([], 3, 2) == [], "no requests render nothing"
assert tile_renders([[0, "north"], [1, "north"], [2, "north"], [3, "north"]], 3, 2) == [[0, "north"], [3, "north"]], "a fresh tile is answered without rendering again"
assert tile_renders([[0, "delta"], [3, "delta"], [4, "delta"]], 4, 3) == [[0, "delta"], [4, "delta"]], "a render goes stale exactly fresh_for ticks on"
assert tile_renders([[0, "a1"], [1, "b2"], [2, "c3"], [3, "a1"]], 100, 2) == [[0, "a1"], [1, "b2"], [2, "c3"], [3, "a1"]], "a tile dropped for room is rendered again"
assert tile_renders([[0, "bay"], [0, "arc"], [1, "cog"], [2, "bay"]], 100, 2) == [[0, "bay"], [0, "arc"], [1, "cog"]], "the oldest render is dropped, a tie going to the first name"


def rejects(*args):
    try:
        tile_renders(*args)
    except ValueError:
        return True
    return False


assert rejects([], 0, 2), "a fresh_for below one is rejected"
print("ok")
