def rebuild_from_last_column(column: str, home: int) -> str:
    if not isinstance(column, str):
        raise ValueError("the column must be a string")
    if len(column) == 0:
        raise ValueError("the column must not be empty")
    for letter in column:
        if not ("a" <= letter <= "z"):
            raise ValueError("the column holds a letter outside a to z")
    if not isinstance(home, int) or isinstance(home, bool):
        raise ValueError("the home must be a whole number")
    if home < 0 or home >= len(column):
        raise ValueError("the home is outside the column")
    width = len(column)
    seats = sorted(range(width), key=lambda place: (column[place], place))
    seat = home
    pieces = []
    for _step in range(width):
        seat = seats[seat]
        pieces.append(column[seat])
    return "".join(pieces)
