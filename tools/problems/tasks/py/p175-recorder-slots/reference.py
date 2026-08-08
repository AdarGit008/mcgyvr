def recorder_snapshot(slots, script):
    if not isinstance(slots, int) or isinstance(slots, bool) or slots < 1:
        raise ValueError("the slot count must be a positive whole number")
    if not isinstance(script, list):
        raise ValueError("the script must be a list")
    seats = [-1] * slots
    head = 0
    carried = 0
    overwritten = 0
    starved = 0
    for entry in script:
        if not isinstance(entry, int) or isinstance(entry, bool) or entry < -1:
            raise ValueError("a script entry must be -1 or a frame number")
        if entry == -1:
            if carried == 0:
                starved += 1
            else:
                head = (head + 1) % slots
                carried -= 1
        elif carried == slots:
            seats[head] = entry
            head = (head + 1) % slots
            overwritten += 1
        else:
            seats[(head + carried) % slots] = entry
            carried += 1
    order = [seats[(head + at) % slots] for at in range(carried)]
    return {
        "order": order,
        "head": head,
        "overwritten": overwritten,
        "starved": starved,
    }
