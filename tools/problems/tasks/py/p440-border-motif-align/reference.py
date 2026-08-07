def _is_count(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def align_border_motifs(widths: list, pattern_length: int) -> dict:
    if not isinstance(widths, list):
        raise ValueError("the widths are a list")
    if not widths:
        raise ValueError("the wall carries no strips")
    if not _is_count(pattern_length):
        raise ValueError("the pattern length is a whole number of one or more")

    edges: list = []
    running = 0
    for width in widths:
        if not _is_count(width):
            raise ValueError("a strip width is a whole number of one or more")
        edges.append(running % pattern_length)
        running += width

    fresh_at = 0
    for index in range(1, len(edges)):
        if edges[index] == 0:
            fresh_at = index + 1
            break
    return {"edges": edges, "freshAt": fresh_at}
