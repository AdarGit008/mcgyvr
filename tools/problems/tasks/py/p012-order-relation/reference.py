def order_relation(pairs: list[list[str]], x: str, y: str) -> str:
    if x == y:
        raise ValueError("query items must differ")
    outgoing: dict[str, list[str]] = {}
    known = set()
    for a, b in pairs:
        known.add(a)
        known.add(b)
        outgoing.setdefault(a, []).append(b)
    if x not in known or y not in known:
        raise ValueError("query items must appear in some pair")

    def reaches(source: str, goal: str) -> bool:
        seen = {source}
        stack = [source]
        while stack:
            node = stack.pop()
            for out in outgoing.get(node, ()):
                if out == goal:
                    return True
                if out not in seen:
                    seen.add(out)
                    stack.append(out)
        return False

    forward = reaches(x, y)
    backward = reaches(y, x)
    if forward and backward:
        return "both"
    if forward:
        return "before"
    if backward:
        return "after"
    return "unordered"
