def pair_off(marks: list[str]) -> list[str]:
    left = []
    for mark in marks:
        if len(left) > 0 and left[len(left) - 1] == mark:
            left.pop()
        else:
            left.append(mark)
    return left
