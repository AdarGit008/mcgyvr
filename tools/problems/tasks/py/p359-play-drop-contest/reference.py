SLANTS = [(0, 1), (1, 0), (1, 1), (1, -1)]


def play_drop_contest(columns: int, rows: int, moves: list) -> dict:
    for size in (columns, rows):
        if not isinstance(size, int) or isinstance(size, bool) or size < 1:
            raise ValueError("the board sides must be whole numbers of one or more")
    if not isinstance(moves, list):
        raise ValueError("the moves must be a list")
    grid = [["."] * columns for _ in range(rows)]
    winner = "none"
    played = 0

    def runs_four(row, column, mark):
        for down, across in SLANTS:
            total = 1
            for sense in (1, -1):
                step = 1
                while True:
                    near_row = row + down * step * sense
                    near_column = column + across * step * sense
                    if not (0 <= near_row < rows and 0 <= near_column < columns):
                        break
                    if grid[near_row][near_column] != mark:
                        break
                    total += 1
                    step += 1
            if total >= 4:
                return True
        return False

    for move in moves:
        if winner != "none":
            break
        if not isinstance(move, int) or isinstance(move, bool):
            raise ValueError("every move must be a whole number")
        if move < 0 or move >= columns:
            raise ValueError("the move names no column")
        landing = -1
        for row in range(rows - 1, -1, -1):
            if grid[row][move] == ".":
                landing = row
                break
        if landing < 0:
            raise ValueError("the column is already full")
        mark = "r" if played % 2 == 0 else "y"
        grid[landing][move] = mark
        played += 1
        if runs_four(landing, move, mark):
            winner = mark
    return {
        "winner": winner,
        "played": played,
        "board": ["".join(row) for row in grid],
    }
