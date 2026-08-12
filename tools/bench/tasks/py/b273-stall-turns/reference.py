def stall_turns(counts: list, limit: int) -> int:
    turns = 0
    for count in counts:
        if count > 0:
            turns += (count + limit - 1) // limit
    return turns
