from collections import deque


def _whole(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def sweep_arena_blocks(slots: list[dict], anchors: list[int]) -> dict:
    if not isinstance(slots, list):
        raise ValueError("sweep_arena_blocks expects an arena list")
    if not isinstance(anchors, list):
        raise ValueError("sweep_arena_blocks expects an anchors list")

    def in_arena(value) -> bool:
        return _whole(value) and 0 <= value < len(slots)

    for slot in slots:
        if not isinstance(slot, dict):
            raise ValueError("every arena entry must be a slot")
        if not _whole(slot.get("size")) or slot["size"] <= 0:
            raise ValueError("a slot size is a whole number above zero")
        if not isinstance(slot.get("links"), list):
            raise ValueError("a slot needs a links list")
        cleanup = slot.get("cleanup")
        if cleanup is not None and not isinstance(cleanup, str):
            raise ValueError("a cleanup is a name or null")
        for link in slot["links"]:
            if not in_arena(link):
                raise ValueError(f"link names no slot of this arena: {link}")

    marked: set[int] = set()
    queue: deque[int] = deque()
    for anchor in anchors:
        if not in_arena(anchor):
            raise ValueError(f"anchor names no slot of this arena: {anchor}")
        if anchor not in marked:
            marked.add(anchor)
            queue.append(anchor)
    while queue:
        here = queue.popleft()
        for link in slots[here]["links"]:
            if link not in marked:
                marked.add(link)
                queue.append(link)

    blocks: list[list[int]] = []
    cleanups: list[str] = []
    reclaimed = 0
    open_at = -1
    bytes_here = 0
    for at, slot in enumerate(slots):
        if at in marked:
            if open_at >= 0:
                blocks.append([open_at, bytes_here])
                open_at = -1
                bytes_here = 0
            continue
        if open_at < 0:
            open_at = at
            bytes_here = 0
        bytes_here += slot["size"]
        reclaimed += slot["size"]
        if slot["cleanup"] is not None:
            cleanups.append(slot["cleanup"])
    if open_at >= 0:
        blocks.append([open_at, bytes_here])
    return {"blocks": blocks, "reclaimed": reclaimed, "cleanups": cleanups}
