def relay_splits(marks: list) -> list:
    splits = []
    previous = 0
    for mark in marks:
        if mark <= previous:
            raise ValueError("clock reading did not advance: " + str(mark))
        splits.append(mark - previous)
        previous = mark
    return splits
