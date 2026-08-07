def rollup_totals(nodes: dict[str, dict]) -> dict[str, int]:
    roots = []
    children: dict[str, list[str]] = {}
    for node_id, node in nodes.items():
        up = node["parent"]
        if up == "":
            roots.append(node_id)
        elif up not in nodes:
            raise ValueError(f"unknown parent {up}")
        else:
            children.setdefault(up, []).append(node_id)
    if len(roots) != 1:
        raise ValueError("the hierarchy needs exactly one root")

    totals: dict[str, int] = {}
    visited = 0

    def subtree(node_id: str) -> int:
        nonlocal visited
        visited += 1
        total = nodes[node_id]["value"]
        for kid in children.get(node_id, ()):
            total += subtree(kid)
        totals[node_id] = total
        return total

    subtree(roots[0])
    if visited != len(nodes):
        raise ValueError("some nodes cannot be reached from the root")
    return totals
