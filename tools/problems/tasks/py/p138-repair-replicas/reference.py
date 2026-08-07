def repair_replicas(replicas):
    if not isinstance(replicas, list) or not replicas:
        raise ValueError("the replica list must be non-empty")
    width = len(replicas[0])
    for replica in replicas:
        if not isinstance(replica, list) or len(replica) != width:
            raise ValueError("replica arrays differ in length")
        for slot in replica:
            if slot is not None and (
                not isinstance(slot, int) or isinstance(slot, bool)
            ):
                raise ValueError("a slot must hold an integer or None")
    rebuilt = []
    for position in range(width):
        tally = {}
        surviving = 0
        for replica in replicas:
            slot = replica[position]
            if slot is None:
                continue
            surviving += 1
            tally[slot] = tally.get(slot, 0) + 1
        if surviving == 0:
            raise ValueError("a position is lost in every replica")
        winner = None
        for value, count in tally.items():
            if count * 2 > surviving:
                winner = value
        if winner is None:
            raise ValueError("no strict majority at some position")
        rebuilt.append(winner)
    return rebuilt
