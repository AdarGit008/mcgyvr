def _check_stride(items, step, offset):
    if not isinstance(items, list):
        raise ValueError("items must be a list")
    if isinstance(step, bool) or not isinstance(step, int) or step < 1:
        raise ValueError("step must be a positive integer")
    if isinstance(offset, bool) or not isinstance(offset, int):
        raise ValueError("offset must be an integer in [0, step)")
    if not 0 <= offset < step:
        raise ValueError("offset must be an integer in [0, step)")


def stride_take(items, step, offset):
    _check_stride(items, step, offset)
    return [item for index, item in enumerate(items) if index % step == offset]


def stride_skip(items, step, offset):
    _check_stride(items, step, offset)
    return [item for index, item in enumerate(items) if index % step != offset]


def stride_weave(parts):
    if not isinstance(parts, list):
        raise ValueError("parts must be a list")
    for part in parts:
        if not isinstance(part, list):
            raise ValueError("every part must be a list")
    woven = []
    cursors = [0] * len(parts)
    remaining = sum(len(part) for part in parts)
    while remaining:
        for index, part in enumerate(parts):
            if cursors[index] < len(part):
                woven.append(part[cursors[index]])
                cursors[index] += 1
                remaining -= 1
    return woven
