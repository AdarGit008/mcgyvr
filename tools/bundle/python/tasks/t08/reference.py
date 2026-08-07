def topo_sort(n: int, edges: list[tuple[int, int]]) -> list[int]:
    """Kahn's algorithm; raises ValueError on a cycle."""
    indegree = [0] * n
    adjacent: list[list[int]] = [[] for _ in range(n)]
    for a, b in edges:
        adjacent[a].append(b)
        indegree[b] += 1
    queue = [v for v in range(n) if indegree[v] == 0]
    order: list[int] = []
    while queue:
        v = queue.pop()
        order.append(v)
        for w in adjacent[v]:
            indegree[w] -= 1
            if indegree[w] == 0:
                queue.append(w)
    if len(order) != n:
        raise ValueError("graph contains a cycle")
    return order
