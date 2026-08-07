def _whole(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def preload_picks(entries: object, room: object) -> list:
    if not isinstance(entries, list):
        raise ValueError("the candidate list must be a list")
    if not _whole(room) or room < 0:
        raise ValueError("the room must be a non-negative whole number")
    keys = set()
    candidates = []
    for raw in entries:
        if not isinstance(raw, dict):
            raise ValueError("a candidate must be a mapping")
        key = raw.get("key")
        if not isinstance(key, str) or not key:
            raise ValueError("a key must be a non-empty string")
        if key in keys:
            raise ValueError("two candidates share a key")
        keys.add(key)
        size = raw.get("size")
        hits = raw.get("hits")
        if not _whole(size) or size < 1:
            raise ValueError("a size must be a positive whole number")
        if not _whole(hits) or hits < 0:
            raise ValueError("hits must be a non-negative whole number")
        candidates.append((key, size, hits))
    candidates.sort(key=lambda row: (-row[2], row[1], row[0]))
    free = room
    taken = []
    for key, size, _hits in candidates:
        if size <= free:
            free -= size
            taken.append(key)
    return taken
