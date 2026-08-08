def seat_parties(rows: list, parties: list) -> list:
    used = [0] * len(rows)
    longest = max(rows, default=0)
    records: list = []
    for size in parties:
        if size < 1:
            raise ValueError("party size below 1")
        if size > longest:
            records.append("rejected:too_big")
            continue
        seated = False
        for i, length in enumerate(rows):
            if length - used[i] >= size:
                records.append(f"{i + 1}-{used[i] + 1}")
                used[i] += size
                seated = True
                break
        if not seated:
            records.append("rejected:full")
    return records
