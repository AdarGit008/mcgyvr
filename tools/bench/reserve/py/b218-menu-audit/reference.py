"""Collect the complaints a café menu's shape earns, in walking order."""


def audit_menu(root: dict, max_depth: int) -> list[str]:
    if isinstance(max_depth, bool) or not isinstance(max_depth, int) or max_depth < 0:
        raise ValueError("max_depth must be a whole number of at least 0")
    complaints: list[str] = []

    def visit(node: dict, above: list[str], twin: bool) -> None:
        trail = " > ".join(above + [node["label"]])
        if node["label"].strip() == "":
            complaints.append(trail + ": blank label")
        if twin:
            complaints.append(trail + ": duplicate")
        if len(above) > max_depth:
            complaints.append(trail + ": too deep")
        seen: set[str] = set()
        for item in node["items"]:
            visit(item, above + [node["label"]], item["label"] in seen)
            seen.add(item["label"])

    visit(root, [], False)
    return complaints
