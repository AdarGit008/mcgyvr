def step_accrual_ledger(opening: int, steps: list[list[int]]) -> list[list[int]]:
    if not isinstance(opening, int) or isinstance(opening, bool) or opening < 0:
        raise ValueError("the opening balance must be whole cents, not below zero")
    if not isinstance(steps, list) or not steps:
        raise ValueError("the schedule must be a non-empty list of steps")

    divisor = 10000 * 365
    rows: list[list[int]] = []
    principal = opening
    heap = 0
    leftover = 0

    for step in steps:
        if not isinstance(step, list) or len(step) != 3:
            raise ValueError("a step is three values long")
        for value in step:
            if not isinstance(value, int) or isinstance(value, bool):
                raise ValueError("every value in a step is a whole number")
        day_count, ten_thousandths, capitalise = step
        if day_count < 1:
            raise ValueError("a step spans at least one day")
        if ten_thousandths < 0:
            raise ValueError("a rate must not be below zero")
        if capitalise not in (0, 1):
            raise ValueError("capitalise is 0 or 1")

        pot = principal * ten_thousandths * day_count + leftover
        earned = pot // divisor
        leftover = pot - earned * divisor
        if capitalise == 1:
            principal += earned
        else:
            heap += earned
        rows.append([earned, principal, heap])
    return rows
