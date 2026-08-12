def widest_list(lanes):
    widest = 0
    for lane in lanes:
        if len(lane) > widest:
            widest = len(lane)
    return widest


def weave_rounds(lanes):
    if not isinstance(lanes, list):
        raise ValueError("weave_rounds expects a list of lanes")
    for lane in lanes:
        if not isinstance(lane, list):
            raise ValueError("every lane must be a list")
    woven = []
    for round_index in range(widest_list(lanes)):
        for lane in lanes:
            if round_index < len(lane):
                woven.append(lane[round_index])
    return woven
