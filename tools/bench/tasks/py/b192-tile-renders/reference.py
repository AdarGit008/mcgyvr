"""Replay tile requests against a size-limited cache of fresh renders."""


def tile_renders(requests: list, fresh_for: int, size: int) -> list:
    for count in (fresh_for, size):
        if isinstance(count, bool) or not isinstance(count, int) or count < 1:
            raise ValueError("fresh_for and size must be positive integers")
    held = {}
    renders = []
    for tick, name in requests:
        since = held.get(name)
        if since is not None and tick < since + fresh_for:
            continue
        if since is None and len(held) == size:
            del held[min(held, key=lambda other: (held[other], other))]
        held[name] = tick
        renders.append([tick, name])
    return renders
