def slot_fill(labels: list, slots: int) -> list:
    """Labels laid across a board of a fixed number of slots."""
    board = []
    for i in range(slots):
        if i < len(labels):
            if labels[i] == "":
                raise ValueError("a label must not be empty")
            board.append(labels[i])
        else:
            board.append("")
    return board
