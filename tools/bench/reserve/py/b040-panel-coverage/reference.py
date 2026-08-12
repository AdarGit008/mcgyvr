"""Coverage statistics for axis-aligned panels laid over an integer grid."""


def panel_coverage(panels: list) -> dict:
    if not isinstance(panels, list):
        raise ValueError("panels must be a list")
    for panel in panels:
        if not isinstance(panel, list) or len(panel) != 4:
            raise ValueError("each panel is an [x1, y1, x2, y2] list")
        for edge in panel:
            if isinstance(edge, bool) or not isinstance(edge, int):
                raise ValueError("panel coordinates must be integers")
        if panel[0] >= panel[2] or panel[1] >= panel[3]:
            raise ValueError("panel edges must be in increasing order")
    if not panels:
        return {"union": 0, "overlap": 0, "deepest": 0, "perimeter": 0, "bounds": None}
    # Compress the plane at every panel edge; inside one compressed cell
    # the stack of panels over any point is constant.
    xs = sorted({edge for panel in panels for edge in (panel[0], panel[2])})
    ys = sorted({edge for panel in panels for edge in (panel[1], panel[3])})
    covered = [[False] * len(ys) for _ in xs]
    union = 0
    overlap = 0
    deepest = 0
    for i in range(len(xs) - 1):
        for j in range(len(ys) - 1):
            depth = 0
            for p in panels:
                if (
                    p[0] <= xs[i]
                    and xs[i + 1] <= p[2]
                    and p[1] <= ys[j]
                    and ys[j + 1] <= p[3]
                ):
                    depth += 1
            area = (xs[i + 1] - xs[i]) * (ys[j + 1] - ys[j])
            if depth >= 1:
                union += area
                covered[i][j] = True
            if depth >= 2:
                overlap += area
            if depth > deepest:
                deepest = depth
    # The union's boundary: each covered cell contributes the sides that
    # face uncovered ground or the outside; seams between covered cells
    # are interior and add nothing.
    perimeter = 0
    for i in range(len(xs) - 1):
        for j in range(len(ys) - 1):
            if not covered[i][j]:
                continue
            width = xs[i + 1] - xs[i]
            height = ys[j + 1] - ys[j]
            if i == 0 or not covered[i - 1][j]:
                perimeter += height
            if i + 2 == len(xs) or not covered[i + 1][j]:
                perimeter += height
            if j == 0 or not covered[i][j - 1]:
                perimeter += width
            if j + 2 == len(ys) or not covered[i][j + 1]:
                perimeter += width
    bounds = [
        min(p[0] for p in panels),
        min(p[1] for p in panels),
        max(p[2] for p in panels),
        max(p[3] for p in panels),
    ]
    return {
        "union": union,
        "overlap": overlap,
        "deepest": deepest,
        "perimeter": perimeter,
        "bounds": bounds,
    }
