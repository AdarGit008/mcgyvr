def polygon_double_area(vertices: list[list[int]]) -> int:
    if not isinstance(vertices, list) or len(vertices) < 3:
        raise ValueError("a polygon needs at least three vertices")
    for vertex in vertices:
        if (
            not isinstance(vertex, list)
            or len(vertex) != 2
            or not all(
                isinstance(c, int) and not isinstance(c, bool) for c in vertex
            )
        ):
            raise ValueError("each vertex must be a pair of two integers")
    count = len(vertices)
    for i in range(count):
        if vertices[i] == vertices[(i + 1) % count]:
            raise ValueError("adjacent vertices must be distinct")
    doubled = 0
    for i in range(count):
        ax, ay = vertices[i]
        bx, by = vertices[(i + 1) % count]
        doubled += ax * by - bx * ay
    return abs(doubled)
