def union_coverage(rects: list[list[int]]) -> int:
    if not isinstance(rects, list):
        raise ValueError("union_coverage expects a list of rectangles")
    for rect in rects:
        if (
            not isinstance(rect, list)
            or len(rect) != 4
            or any(not isinstance(c, int) or isinstance(c, bool) for c in rect)
        ):
            raise ValueError("each rectangle must be four integers")
        x1, y1, x2, y2 = rect
        if x1 >= x2 or y1 >= y2:
            raise ValueError("rectangle corners must satisfy x1 < x2 and y1 < y2")
        if any(c < -10000 or c > 10000 for c in rect):
            raise ValueError("coordinates must stay within -10000..10000")
    if not rects:
        return 0
    xs = sorted({c for r in rects for c in (r[0], r[2])})
    ys = sorted({c for r in rects for c in (r[1], r[3])})
    area = 0
    for i in range(len(xs) - 1):
        for j in range(len(ys) - 1):
            covered = any(
                r[0] <= xs[i] and xs[i + 1] <= r[2] and r[1] <= ys[j] and ys[j + 1] <= r[3]
                for r in rects
            )
            if covered:
                area += (xs[i + 1] - xs[i]) * (ys[j + 1] - ys[j])
    return area
