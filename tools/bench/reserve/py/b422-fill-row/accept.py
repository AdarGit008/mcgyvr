from solution import blank_row, fill_rows


def rejects(width):
    try:
        blank_row(width)
    except Exception:
        return True
    return False


assert blank_row(3) == [0, 0, 0], "a row of zeros"
assert blank_row(0) == [], "a row of no width"
assert fill_rows(2, 2) == [[0, 0], [0, 0]], "two rows"
assert fill_rows(0, 3) == [], "no rows at all"

grid = fill_rows(2, 2)
grid[0][0] = 9
assert grid[1] == [0, 0], "writing into one row leaves the other alone"
assert rejects(-1), "a negative width is rejected"
print("ok")
