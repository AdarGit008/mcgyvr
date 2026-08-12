def poll_gaps(minutes: list) -> list:
    if len(minutes) < 2:
        return []
    ran = set(minutes)
    missing = []
    for minute in range(minutes[0], minutes[-1]):
        if minute not in ran:
            missing.append(minute)
    return missing
