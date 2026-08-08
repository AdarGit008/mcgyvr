def _assert_siblings(node: dict) -> None:
    seen = set()
    for child in node["children"]:
        if child["name"] in seen:
            raise ValueError("duplicate sibling name: " + child["name"])
        seen.add(child["name"])
        _assert_siblings(child)


def _add_all(node: dict, path: str, out: list) -> None:
    out.append({"op": "add", "path": path, "value": node["value"]})
    for child in node["children"]:
        _add_all(child, path + "/" + child["name"], out)


def _walk(before: dict, after: dict, path: str, out: list) -> None:
    if before["value"] != after["value"]:
        out.append(
            {
                "op": "change",
                "path": path,
                "from": before["value"],
                "to": after["value"],
            }
        )
    olds = {child["name"]: child for child in before["children"]}
    kept = {child["name"] for child in after["children"]}
    for child in after["children"]:
        child_path = path + "/" + child["name"]
        prior = olds.get(child["name"])
        if prior is not None:
            _walk(prior, child, child_path, out)
        else:
            _add_all(child, child_path, out)
    for child in before["children"]:
        if child["name"] not in kept:
            out.append({"op": "remove", "path": path + "/" + child["name"]})


def tree_delta(before: dict, after: dict) -> list:
    if before["name"] != after["name"]:
        raise ValueError("root names differ")
    _assert_siblings(before)
    _assert_siblings(after)
    out: list = []
    _walk(before, after, before["name"], out)
    return out
