def collate_feeds(feeds):
    entries = []
    for index, feed in enumerate(feeds):
        previous = None
        for tick, reading in feed:
            if previous is not None and tick <= previous:
                raise ValueError(f"feed {index} ticks are not strictly increasing")
            previous = tick
            entries.append((tick, index, reading))
    entries.sort(key=lambda entry: (entry[0], entry[1]))
    timeline = []
    last_tick = None
    for tick, _, reading in entries:
        if tick == last_tick:
            continue
        last_tick = tick
        if timeline and timeline[-1][1] == reading:
            continue
        timeline.append([tick, reading])
    return timeline
