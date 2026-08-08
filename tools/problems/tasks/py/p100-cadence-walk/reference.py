from collections import deque


def label_cadence_walk(
    edges: list[list[str]], cadence: list[str], start: str, goal: str
) -> int:
    if not isinstance(cadence, list) or not cadence:
        raise ValueError("cadence must be a non-empty list")
    for step in cadence:
        if not isinstance(step, str) or step == "":
            raise ValueError("cadence entries must be non-empty strings")
    nodes = set()
    for edge in edges:
        if (
            not isinstance(edge, list)
            or len(edge) != 3
            or any(not isinstance(part, str) or part == "" for part in edge)
        ):
            raise ValueError("each edge must be a [from, to, label] triple of non-empty strings")
        nodes.add(edge[0])
        nodes.add(edge[1])
    if start not in nodes:
        raise ValueError("start appears in no edge")
    if goal not in nodes:
        raise ValueError("goal appears in no edge")
    if start == goal:
        return 0
    queue = deque([(start, 0, 0)])
    visited = {(start, 0)}
    while queue:
        node, index, steps = queue.popleft()
        for source, target, label in edges:
            if source != node or label != cadence[index]:
                continue
            if target == goal:
                return steps + 1
            next_index = (index + 1) % len(cadence)
            if (target, next_index) not in visited:
                visited.add((target, next_index))
                queue.append((target, next_index, steps + 1))
    return -1
