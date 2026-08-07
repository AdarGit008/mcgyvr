def leaf_paths(rows: list[list[str]]) -> list[str]:
    if not rows:
        raise ValueError("the hierarchy is empty")
    parent: dict[str, str] = {}
    for node_id, up in rows:
        if node_id in parent:
            raise ValueError(f"duplicated id {node_id}")
        parent[node_id] = up
    roots = []
    children: dict[str, list[str]] = {}
    for node_id, up in rows:
        if up == "":
            roots.append(node_id)
        elif up not in parent:
            raise ValueError(f"unknown parent {up}")
        else:
            children.setdefault(up, []).append(node_id)
    if len(roots) != 1:
        raise ValueError("the hierarchy needs exactly one root")

    paths: list[str] = []
    visited = 0

    def walk(node_id: str, prefix: str) -> None:
        nonlocal visited
        visited += 1
        here = node_id if prefix == "" else f"{prefix}/{node_id}"
        kids = children.get(node_id, [])
        if not kids:
            paths.append(here)
            return
        for kid in kids:
            walk(kid, here)

    walk(roots[0], "")
    if visited != len(rows):
        raise ValueError("some rows cannot be reached from the root")
    return sorted(paths)
