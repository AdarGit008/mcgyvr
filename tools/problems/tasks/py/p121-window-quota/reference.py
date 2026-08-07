def window_quota(limit: int, width: int, calls: list) -> list:
    if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
        raise ValueError("limit must be a positive integer")
    if not isinstance(width, int) or isinstance(width, bool) or width <= 0:
        raise ValueError("width must be a positive integer")
    served = {}
    current_frame = None
    previous = None
    labels = []
    for call in calls:
        time, name = call[0], call[1]
        if not isinstance(time, int) or isinstance(time, bool) or time < 0:
            raise ValueError("time must be a non-negative integer")
        if previous is not None and time < previous:
            raise ValueError("times must not decrease")
        if not isinstance(name, str) or name == "":
            raise ValueError("name must be a non-empty string")
        previous = time
        frame = time // width
        if frame != current_frame:
            served = {}
            current_frame = frame
        used = served.get(name, 0)
        if used < limit:
            labels.append("ok")
            served[name] = used + 1
        else:
            labels.append("over")
    return labels
