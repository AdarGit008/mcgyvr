def _whole(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _validate(raw, where: str):
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError(where + " is neither a node nor nothing")
    for entry in ("key", "count", "left", "right"):
        if entry not in raw:
            raise ValueError(where + " lacks the entry " + entry)
    if not _whole(raw["key"]):
        raise ValueError(where + " has a key that is not a whole number")
    if not _whole(raw["count"]) or raw["count"] <= 0:
        raise ValueError(where + " has a count that is not a positive whole number")
    _validate(raw["left"], where + "/L")
    _validate(raw["right"], where + "/R")
    return raw


def _stats(node) -> tuple:
    if node is None:
        return (0, 0, [])
    left_depth, left_size, left_keys = _stats(node["left"])
    right_depth, right_size, right_keys = _stats(node["right"])
    return (
        1 + max(left_depth, right_depth),
        1 + left_size + right_size,
        [node["key"], *left_keys, *right_keys],
    )


def _inspect(node: dict, path: str):
    left_depth, left_size, left_keys = _stats(node["left"])
    right_depth, right_size, right_keys = _stats(node["right"])
    if any(key >= node["key"] for key in left_keys) or any(
        key <= node["key"] for key in right_keys
    ):
        return {"path": path, "rule": "order"}
    if abs(left_depth - right_depth) > 1:
        return {"path": path, "rule": "balance"}
    if node["count"] != 1 + left_size + right_size:
        return {"path": path, "rule": "count"}
    if node["left"] is not None:
        below = _inspect(node["left"], path + "/L")
        if below is not None:
            return below
    if node["right"] is not None:
        below = _inspect(node["right"], path + "/R")
        if below is not None:
            return below
    return None


def first_broken_rule(root: dict) -> dict:
    node = _validate(root, "root")
    if node is None:
        raise ValueError("there is no root to inspect")
    found = _inspect(node, "root")
    return found if found is not None else {"path": "", "rule": "sound"}
