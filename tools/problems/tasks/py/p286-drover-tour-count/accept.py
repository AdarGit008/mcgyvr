from solution import count_piece_tours

assert count_piece_tours(1, 1, [0, 0], []) == 1, (
    "a board of one square is already toured"
)
assert count_piece_tours(3, 1, [0, 0], []) == 1, (
    "a single row admits only the walk to its far end"
)
assert count_piece_tours(2, 2, [0, 0], []) == 2, (
    "the four corners of a small board, two ways round"
)
assert count_piece_tours(2, 2, [0, 0], [[1, 1]]) == 0, (
    "blocking a corner strands the two squares beside it"
)
assert count_piece_tours(2, 3, [0, 0], []) == 3, "two columns of three rows"
assert count_piece_tours(3, 3, [0, 0], []) == 22, (
    "a nine-square board started at a corner"
)
assert count_piece_tours(3, 3, [1, 1], []) == 16, (
    "the same board started at its middle"
)
assert count_piece_tours(3, 3, [0, 0], [[1, 1]]) == 2, (
    "blocking the middle leaves only a rim to walk"
)
assert count_piece_tours(3, 3, [0, 0], [[0, 1], [1, 0]]) == 4, (
    "walling in the start square forces the opening leap"
)
assert count_piece_tours(3, 4, [0, 0], []) == 194, "the widest board the rules allow"
assert count_piece_tours(4, 4, [0, 0], [[0, 3], [1, 3], [2, 3], [3, 3]]) == 194, (
    "blocking a whole column reproduces the narrower board"
)


def rejects(width, height, start, blocked):
    try:
        count_piece_tours(width, height, start, blocked)
    except ValueError:
        return True
    return False


assert rejects(0, 2, [0, 0], []), "a board with no columns"
assert rejects(2, 2.5, [0, 0], []), "a fractional row count"
assert rejects(4, 4, [0, 0], []), "too many open squares"
assert rejects(2, 2, [0, 2], []), "start off the board"
assert rejects(2, 2, [0, 0], [[0, 0]]), "start on a blocked square"
assert rejects(2, 2, [0, 0], [[0, 5]]), "a blocked square off the board"
assert rejects(2, 2, [0, 0], [[0, 1], [0, 1]]), "the same square blocked twice"
assert rejects(2, 2, [0, 0], "x"), "blocked is not a list"
assert rejects(2, 2, [0], []), "start is not a pair"
print("ok")
