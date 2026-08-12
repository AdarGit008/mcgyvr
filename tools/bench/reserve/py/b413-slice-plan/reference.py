def slice_end(start: int, width: int, total: int) -> int:
    end = start + width
    return total if end > total else end


def slice_plan(total: int, width: int) -> list:
    plan = []
    start = 0
    while start < total:
        plan.append([start, slice_end(start, width, total)])
        start += width
    return plan
