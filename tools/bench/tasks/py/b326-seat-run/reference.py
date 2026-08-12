def seat_run(row: str, party: int) -> int:
    run = 0
    for i, seat in enumerate(row):
        run = run + 1 if seat == "." else 0
        if run == party:
            return i - party + 1
    return -1
