def _whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _in_range(value):
    return abs(value) <= 1000000


def _divisor(a, b):
    while b:
        a, b = b, a % b
    return a


def _render(num, den):
    if num == 0:
        return "0"
    shared = _divisor(abs(num), den)
    top = num // shared
    bottom = den // shared
    return str(top) if bottom == 1 else f"{top}/{bottom}"


def calibrate_raw_count(table: list, raw: int) -> str:
    if not _whole(raw):
        raise ValueError("the raw count is not a whole number")
    if not _in_range(raw):
        raise ValueError("the raw count reaches beyond a million away from nought")
    if not isinstance(table, list):
        raise ValueError("calibrate_raw_count expects a list of rows")
    if len(table) < 2:
        raise ValueError("the table holds fewer than two rows")
    for row in table:
        if not isinstance(row, list) or len(row) != 2:
            raise ValueError("a row is not a list of exactly two entries")
        for entry in row:
            if not _whole(entry):
                raise ValueError("a row entry is not a whole number")
            if not _in_range(entry):
                raise ValueError("a row entry reaches beyond a million away from nought")
    for earlier, later in zip(table, table[1:]):
        if later[0] <= earlier[0]:
            raise ValueError("the counts do not climb strictly from row to row")

    first = table[0]
    last = table[-1]
    if raw <= first[0]:
        return _render(first[1], 1)
    if raw >= last[0]:
        return _render(last[1], 1)

    index = 0
    while table[index + 1][0] <= raw:
        index += 1
    lo = table[index]
    hi = table[index + 1]
    den = hi[0] - lo[0]
    num = lo[1] * den + (raw - lo[0]) * (hi[1] - lo[1])
    return _render(num, den)
