def run_of(entries: list, start: int) -> int:
    length = 1
    while start + length < len(entries) and entries[start + length] == entries[start]:
        length += 1
    return length


def group_runs(entries: list) -> list:
    """The list broken into runs of equal neighbouring values."""
    runs = []
    i = 0
    while i < len(entries):
        length = run_of(entries, i)
        runs.append(entries[i : i + length])
        i += length
    return runs
