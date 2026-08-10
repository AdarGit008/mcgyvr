def chain_of_command(root: dict, person: str) -> list:
    if not isinstance(person, str) or not person:
        raise ValueError("person must be a non-empty string")
    matches = []

    def walk(node, trail):
        name = node["name"]
        if not isinstance(name, str) or not name:
            raise ValueError("every name must be a non-empty string")
        path = trail + [name]
        if name == person:
            matches.append(path)
        for child in node["reports"]:
            walk(child, path)

    walk(root, [])
    if not matches:
        raise ValueError("person is not in the chart")
    if len(matches) > 1:
        raise ValueError("person appears more than once")
    return matches[0]


def headcount(root: dict) -> int:
    return 1 + sum(headcount(child) for child in root["reports"])


def widest_team(root: dict) -> int:
    widest = len(root["reports"])
    for child in root["reports"]:
        widest = max(widest, widest_team(child))
    return widest
