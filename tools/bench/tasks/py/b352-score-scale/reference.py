def score_scale(mark: int, was_out_of: int, now_out_of: int) -> int:
    if was_out_of <= 0:
        return 0
    scaled = mark * now_out_of // was_out_of
    if scaled > now_out_of:
        return now_out_of
    return scaled
