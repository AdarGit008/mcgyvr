def time_gap(from_hour: int, from_minute: int, to_hour: int, to_minute: int) -> int:
    start = from_hour * 60 + from_minute
    end = to_hour * 60 + to_minute
    if end <= start:
        end += 24 * 60
    return end - start
