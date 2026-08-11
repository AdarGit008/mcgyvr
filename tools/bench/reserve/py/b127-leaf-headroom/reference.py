"""Spendable request units per leaf of a nested quota-group tree."""


def leaf_headroom(tree: dict) -> dict:
    def check_count(value, what):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{what} must be a non-negative integer")
        return value

    def burn_of(node, burns):
        if not isinstance(node, dict):
            raise ValueError("a node must be a plain object")
        check_count(node.get("limit"), "limit")
        if "children" not in node:
            total = check_count(node.get("used"), "a leaf's used")
        else:
            if "used" in node:
                raise ValueError("a group must not carry used")
            children = node["children"]
            if not isinstance(children, dict):
                raise ValueError("children must map names to nodes")
            total = 0
            for name, child in children.items():
                if not isinstance(name, str) or name == "":
                    raise ValueError("a child name must be a non-empty string")
                if "/" in name:
                    raise ValueError(f"a child name must not hold a slash: {name}")
                total += burn_of(child, burns)
        burns[id(node)] = total
        return total

    def collect(node, path, ceiling, burns, into):
        room = min(ceiling, node["limit"] - burns[id(node)])
        if "children" not in node:
            into[path] = max(0, room)
            return
        for name, child in node["children"].items():
            deeper = name if path == "" else f"{path}/{name}"
            collect(child, deeper, room, burns, into)

    if not isinstance(tree, dict) or "children" not in tree:
        raise ValueError("the root must be a quota group")
    burns = {}
    burn_of(tree, burns)
    into = {}
    collect(tree, "", float("inf"), burns, into)
    return into
