"""Vet a device's proposed firmware upgrade path and report the final tag."""


def vet_upgrade_path(installed: str, steps: list) -> str:
    def parse_tag(value):
        if not isinstance(value, str):
            raise ValueError("a tag must be a string")
        parts = value.split(".")
        if len(parts) != 2:
            raise ValueError(f"a tag is line.point: {value}")
        for part in parts:
            if part == "":
                raise ValueError(f"empty tag part: {value}")
            if not part.isdigit():
                raise ValueError(f"a tag part must be plain digits: {value}")
            if len(part) > 1 and part.startswith("0"):
                raise ValueError(f"leading zero in a tag part: {value}")
        return (int(parts[0]), int(parts[1]))

    def older(a, b):
        if a[0] != b[0]:
            return a[0] < b[0]
        return a[1] < b[1]

    carried_tag = installed
    carried = parse_tag(installed)
    if not isinstance(steps, list):
        raise ValueError("steps must be a list")

    for step in steps:
        if not isinstance(step, dict):
            raise ValueError("a step must be an object with tag and requires")
        tag = step.get("tag")
        requires = step.get("requires")
        next_tag = parse_tag(tag)
        floor = parse_tag(requires)
        if older(carried, floor):
            raise ValueError(f"step {tag} requires at least {requires}")
        if next_tag == carried:
            raise ValueError(f"step {tag} repeats the carried tag")
        if older(next_tag, carried):
            raise ValueError(f"step {tag} is a downgrade from {carried_tag}")
        carried_tag = tag
        carried = next_tag
    return carried_tag
