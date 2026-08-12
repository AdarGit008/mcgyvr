def line_up(links: dict[str, str], start: str) -> list[str]:
    line = [start]
    at = start
    while at in links:
        at = links[at]
        if at in line:
            raise ValueError("the links run in a circle")
        line.append(at)
    return line
