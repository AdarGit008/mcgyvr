def time_add(hour: int, minute: int, added: int) -> list:
    total = (hour * 60 + minute + added) % (24 * 60)
    return [total // 60, total % 60]
