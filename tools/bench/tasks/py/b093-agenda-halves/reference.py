def split_agenda(sessions, limit):
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("limit must be a whole number of at least one minute")
    blocks = []

    def halve(low, high):
        if high - low <= limit:
            blocks.append([low, high])
            return
        mid = low + (high - low + 1) // 2
        halve(low, mid)
        halve(mid, high)

    previous_end = None
    for session in sessions:
        start, end = session
        for bound in (start, end):
            if isinstance(bound, bool) or not isinstance(bound, int):
                raise ValueError("session bounds must be whole minutes")
        if start >= end:
            raise ValueError("a session's start must precede its end")
        if previous_end is not None and start < previous_end:
            raise ValueError("sessions must be in order and must not overlap")
        previous_end = end
        halve(start, end)
    return blocks
