from solution import judge_lancer

board = [
    ".......",
    "..W....",
    ".......",
    "..B.WB.",
    "..W....",
    ".......",
    ".......",
]
rest = board[2:]

assert judge_lancer(board, "W", [1, 2], [1, 5]) == "ok", "a clear three-square slide"
assert judge_lancer(board, "W", [1, 2], [3, 2]) == "ok", "capture at range two"
assert (
    judge_lancer(board, "B", [3, 2], [1, 2]) == "ok"
), "black captures upward at range two"
assert (
    judge_lancer([".......", "W..B..."] + rest, "W", [1, 0], [1, 3]) == "ok"
), "capture at full three-square reach"
assert judge_lancer(board, "W", [4, 2], [4, 0]) == "ok", "a quiet two-square slide"
assert (
    judge_lancer(board, "W", [3, 4], [3, 5]) == "too_close"
), "an adjacent enemy cannot be taken"
assert judge_lancer(board, "B", [3, 5], [3, 3]) == "blocked", "sliding across a piece"
assert (
    judge_lancer(board, "W", [1, 2], [4, 2]) == "blocked"
), "the crossed square is checked, not skipped"
assert (
    judge_lancer(board, "W", [4, 2], [1, 2]) == "blocked"
), "blocked works in both directions"
assert (
    judge_lancer([".......", "WWW...."] + rest, "W", [1, 0], [1, 2]) == "blocked"
), "blocked outranks own_piece at the landing"
assert (
    judge_lancer([".......", "W.W...."] + rest, "W", [1, 0], [1, 2]) == "own_piece"
), "landing on one's own lancer"
assert judge_lancer(board, "W", [1, 2], [2, 3]) == "bad_line", "no diagonal slides"
assert judge_lancer(board, "W", [1, 2], [1, 6]) == "bad_line", "four squares is too far"
assert (
    judge_lancer(board, "W", [1, 2], [1, 2]) == "bad_line"
), "standing still is not a move"
assert judge_lancer(board, "W", [3, 3], [3, 2]) == "no_piece", "an empty from square"
assert (
    judge_lancer(board, "W", [3, 2], [3, 1]) == "no_piece"
), "an enemy lancer is not yours to move"
assert (
    judge_lancer(board, "W", [1, 2], [-1, 2]) == "off_board"
), "the to square must be on the board"
assert (
    judge_lancer(board, "W", [7, 2], [6, 2]) == "off_board"
), "off_board outranks no_piece"


def rejects(board, side, origin, dest):
    try:
        judge_lancer(board, side, origin, dest)
    except ValueError:
        return True
    return False


assert rejects(board[1:], "W", [1, 2], [1, 3]), "six rows are rejected"
assert rejects(
    [".......", "..X...."] + rest, "W", [1, 2], [1, 3]
), "a stray character is rejected"
assert rejects(board, "w", [1, 2], [1, 3]), "a lowercase side is rejected"
assert rejects(board, "W", [1], [1, 3]), "a one-number square is rejected"
assert rejects(board, "W", [1, 2], [1, 2.5]), "a fractional coordinate is rejected"
print("ok")
