def _walk(before: dict, after: dict, prefix: str, lines: list) -> None:
    for key in after:
        path = key if prefix == "" else prefix + "/" + key
        if key in before:
            _walk(before[key], after[key], path, lines)
        else:
            lines.append("added " + path)
    for key in before:
        if key not in after:
            path = key if prefix == "" else prefix + "/" + key
            lines.append("removed " + path)


def outline_diff(before: dict, after: dict) -> list:
    lines: list = []
    _walk(before, after, "", lines)
    lines.sort()
    return lines
