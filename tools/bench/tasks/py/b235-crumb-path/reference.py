def crumb_split(trail: str) -> list:
    return [part for part in trail.split("/") if part]


def crumb_join(parts: list) -> str:
    return "/".join(part for part in parts if part)
