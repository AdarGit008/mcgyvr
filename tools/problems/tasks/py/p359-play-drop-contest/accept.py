from solution import play_drop_contest

assert play_drop_contest(7, 6, [0, 0, 1, 1, 2, 2, 3]) == {
    "winner": "r",
    "played": 7,
    "board": [".......", ".......", ".......", ".......", "yyy....", "rrrr..."],
}, "four along a row"
assert play_drop_contest(7, 6, [0, 1, 0, 1, 0, 1, 0]) == {
    "winner": "r",
    "played": 7,
    "board": [".......", ".......", "r......", "ry.....", "ry.....", "ry....."],
}, "four down a column"
assert play_drop_contest(7, 6, [0, 1, 1, 2, 6, 2, 2, 3, 6, 3, 6, 3, 3]) == {
    "winner": "r",
    "played": 13,
    "board": [".......", ".......", "...r...", "..ry..r", ".ryy..r", "ryyy..r"],
}, "four on the slant falling to the left"
assert play_drop_contest(7, 6, [6, 5, 5, 4, 0, 4, 4, 3, 0, 3, 0, 3, 3]) == {
    "winner": "r",
    "played": 13,
    "board": [".......", ".......", "...r...", "r..yr..", "r..yyr.", "r..yyyr"],
}, "four on the slant falling to the right"
assert play_drop_contest(7, 6, [0, 0, 1, 1, 2, 2, 3, 4, 5, 6]) == {
    "winner": "r",
    "played": 7,
    "board": [".......", ".......", ".......", ".......", "yyy....", "rrrr..."],
}, "moves after the win are left undropped"
assert play_drop_contest(7, 6, [3, 3, 4, 4, 5, 5, 6]) == {
    "winner": "r",
    "played": 7,
    "board": [".......", ".......", ".......", ".......", "...yyy.", "...rrrr"],
}, "a win against the right-hand wall"
assert play_drop_contest(7, 6, [0, 1, 0, 1]) == {
    "winner": "none",
    "played": 4,
    "board": [".......", ".......", ".......", ".......", "ry.....", "ry....."],
}, "too few discs to win"
assert play_drop_contest(3, 3, [0, 1, 2, 0, 1, 2, 0, 1, 2]) == {
    "winner": "none",
    "played": 9,
    "board": ["ryr", "yry", "ryr"],
}, "a full board too small to hold four"
assert play_drop_contest(4, 4, []) == {
    "winner": "none",
    "played": 0,
    "board": ["....", "....", "....", "...."],
}, "no moves at all"
assert play_drop_contest(1, 1, [0]) == {
    "winner": "none",
    "played": 1,
    "board": ["r"],
}, "a board of one square"


def rejects(columns, rows, moves):
    try:
        play_drop_contest(columns, rows, moves)
    except ValueError:
        return True
    return False


assert rejects(0, 6, []), "a board with no columns is thrown out"
assert rejects(7, 0, []), "a board with no rows is thrown out"
assert rejects(7.5, 6, []), "a side that is not whole is thrown out"
assert rejects(7, 6, "0"), "moves that are not a list are thrown out"
assert rejects(7, 6, [1.5]), "a move that is not whole is thrown out"
assert rejects(7, 6, [7]), "a move past the last column is thrown out"
assert rejects(7, 6, [-1]), "a move below the first column is thrown out"
assert rejects(1, 2, [0, 0, 0]), "a move into a full column is thrown out"
print("ok")
