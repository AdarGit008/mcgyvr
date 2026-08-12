def locker_gap(used: list) -> int:
    taken = set(used)
    locker = 1
    while locker in taken:
        locker += 1
    return locker
