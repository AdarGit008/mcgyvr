def mend_shards(copies):
    if not isinstance(copies, list) or not copies:
        raise ValueError("the list of copies must be non-empty")
    width = len(copies[0])
    for copy in copies:
        if not isinstance(copy, list) or len(copy) != width:
            raise ValueError("copies differ in length")
        for slot in copy:
            if slot is not None and (
                not isinstance(slot, int) or isinstance(slot, bool) or slot < 0
            ):
                raise ValueError("a slot must be a non-negative integer or None")
    mended = []
    for position in range(width):
        counts = {}
        earliest = {}
        for index, copy in enumerate(copies):
            slot = copy[position]
            if slot is None:
                continue
            counts[slot] = counts.get(slot, 0) + 1
            earliest.setdefault(slot, index)
        if not counts:
            mended.append(-1)
            continue
        winner = min(counts, key=lambda value: (-counts[value], earliest[value]))
        mended.append(winner)
    return mended
