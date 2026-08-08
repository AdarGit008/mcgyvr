def _minor(frame: list[list[int]], skip_row: int, skip_column: int) -> int:
    kept = [
        [entry for column, entry in enumerate(frame[row]) if column != skip_column]
        for row in range(3)
        if row != skip_row
    ]
    return kept[0][0] * kept[1][1] - kept[0][1] * kept[1][0]


def lattice_inverse(frame: list[list[int]]) -> list[list[int]]:
    if not isinstance(frame, list) or len(frame) not in (2, 3):
        raise ValueError("a frame stands exactly two or three rows tall")
    for row in frame:
        if not isinstance(row, list) or len(row) != len(frame):
            raise ValueError("every row must match the frame's height")
        for entry in row:
            if isinstance(entry, bool) or not isinstance(entry, int):
                raise ValueError("every entry must be a whole number")
    if len(frame) == 2:
        determinant = frame[0][0] * frame[1][1] - frame[0][1] * frame[1][0]
        if determinant not in (1, -1):
            return []
        return [
            [frame[1][1] * determinant, -frame[0][1] * determinant],
            [-frame[1][0] * determinant, frame[0][0] * determinant],
        ]
    cofactor = [
        [
            (1 if (row + column) % 2 == 0 else -1) * _minor(frame, row, column)
            for column in range(3)
        ]
        for row in range(3)
    ]
    determinant = sum(frame[0][column] * cofactor[0][column] for column in range(3))
    if determinant not in (1, -1):
        return []
    return [
        [cofactor[column][row] * determinant for column in range(3)]
        for row in range(3)
    ]
