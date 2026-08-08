def admit_bytes(per_key: int, total: int, span: int, entries: list) -> list:
    for limit in (per_key, total, span):
        if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
            raise ValueError("per_key, total and span must be positive integers")
    carried = []
    labels = []
    previous = -1
    for entry in entries:
        time, key, size = entry[0], entry[1], entry[2]
        if not isinstance(time, int) or isinstance(time, bool) or time < 0:
            raise ValueError("time must be a non-negative integer")
        if previous >= 0 and time < previous:
            raise ValueError("times must never decrease")
        if not isinstance(key, str) or key == "":
            raise ValueError("key must be a non-empty string")
        if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
            raise ValueError("size must be a positive integer")
        previous = time
        key_volume = 0
        all_volume = 0
        for when, who, how_much in carried:
            if when > time - span:
                all_volume += how_much
                if who == key:
                    key_volume += how_much
        if key_volume + size <= per_key and all_volume + size <= total:
            labels.append("pass")
            carried.append((time, key, size))
        else:
            labels.append("drop")
    return labels
