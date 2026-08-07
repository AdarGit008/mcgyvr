HEADINGS = [(0, 1), (1, 0), (1, 1), (-1, 1)]


def find_line_of_four(board: list) -> dict:
    if not isinstance(board, list):
        raise ValueError("the board must be a list of lines")
    if len(board) == 0:
        raise ValueError("the board must hold at least one line")
    width = None
    for line in board:
        if not isinstance(line, str):
            raise ValueError("every line must be a string")
        if len(line) == 0:
            raise ValueError("a line must not be empty")
        if width is None:
            width = len(line)
        elif len(line) != width:
            raise ValueError("the lines are not all one length")
        for mark in line:
            if mark not in ("r", "y", "."):
                raise ValueError("a mark is outside r, y and the dot")
    height = len(board)
    for column in range(width):
        for row in range(height - 1):
            if board[row][column] != "." and board[row + 1][column] == ".":
                raise ValueError("a disc hangs over an empty square")
    for row in range(height):
        for column in range(width):
            colour = board[row][column]
            if colour == ".":
                continue
            for down, across in HEADINGS:
                cells = []
                for step in range(4):
                    near_row = row + down * step
                    near_column = column + across * step
                    if not (0 <= near_row < height and 0 <= near_column < width):
                        break
                    if board[near_row][near_column] != colour:
                        break
                    cells.append([near_row, near_column])
                if len(cells) == 4:
                    return {"winner": colour, "cells": cells}
    return {"winner": "none", "cells": []}
