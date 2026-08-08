def space_artist_run(tracks: list) -> list:
    if not isinstance(tracks, list) or not tracks:
        raise ValueError("there must be at least one track")

    queues = {}
    earliest = {}
    seen = set()

    for index, track in enumerate(tracks):
        title = track.get("title")
        artist = track.get("artist")
        if not isinstance(title, str) or title == "":
            raise ValueError("every track needs a title")
        if not isinstance(artist, str) or artist == "":
            raise ValueError(f"the track {title} needs an artist")
        if title in seen:
            raise ValueError(f"the title {title} appears twice")
        seen.add(title)
        if artist not in queues:
            queues[artist] = []
            earliest[artist] = index
        queues[artist].append(title)

    run = []
    previous = None
    for _ in range(len(tracks)):
        choice = None
        best_left = 0
        best_at = 0
        for artist, queue in queues.items():
            if not queue or artist == previous:
                continue
            at = earliest[artist]
            if (
                choice is None
                or len(queue) > best_left
                or (len(queue) == best_left and at < best_at)
            ):
                choice = artist
                best_left = len(queue)
                best_at = at
        if choice is None:
            raise ValueError("no order can keep every artist apart")
        run.append(queues[choice].pop(0))
        previous = choice
    return run
