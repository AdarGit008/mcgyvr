def audit_region_grid(digits: list, territories: list) -> str:
    if not isinstance(digits, list) or not isinstance(territories, list):
        raise ValueError("both boards must be lists of rows")
    side = len(digits)
    if side < 1 or side > 9:
        raise ValueError("the side must be between one and nine")
    if len(territories) != side:
        raise ValueError("the two boards differ in height")

    value = []
    label = []
    for row in range(side):
        digit_row = digits[row]
        label_row = territories[row]
        if not isinstance(digit_row, str) or len(digit_row) != side:
            raise ValueError(f"digit row {row + 1} is not {side} characters wide")
        if not isinstance(label_row, str) or len(label_row) != side:
            raise ValueError(f"label row {row + 1} is not {side} characters wide")
        values = []
        labels = []
        for file in range(side):
            digit = ord(digit_row[file]) - 48
            if digit < 1 or digit > side:
                raise ValueError(
                    f"square {row + 1},{file + 1} is not a digit from 1 to {side}"
                )
            mark = label_row[file]
            if mark < "A" or mark > "Z":
                raise ValueError(
                    f"square {row + 1},{file + 1} carries no uppercase label"
                )
            values.append(digit)
            labels.append(mark)
        value.append(values)
        label.append(labels)

    held = {}
    for row in range(side):
        for file in range(side):
            held.setdefault(label[row][file], []).append(value[row][file])
    marks = sorted(held)
    if len(marks) != side:
        raise ValueError(f"the labelling makes {len(marks)} territories, not {side}")
    for mark in marks:
        if len(held[mark]) != side:
            raise ValueError(f"territory {mark} does not hold {side} squares")

    def complete(group):
        return len(set(group)) == side

    for row in range(side):
        if not complete(value[row]):
            return f"row {row + 1}"
    for file in range(side):
        if not complete([value[row][file] for row in range(side)]):
            return f"file {file + 1}"
    for mark in marks:
        if not complete(held[mark]):
            return f"territory {mark}"
    return "ok"
