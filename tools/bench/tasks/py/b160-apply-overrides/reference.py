def apply_overrides(base: dict, overrides: list) -> dict:
    if not isinstance(overrides, list):
        raise ValueError("overrides must be a list")
    merged = dict(base)
    for line in overrides:
        if not isinstance(line, str):
            raise ValueError("an override must be a string")
        at = line.find("=")
        if at < 1:
            raise ValueError("an override needs a non-empty name, an equals sign and a value")
        name = line[:at]
        if name not in base:
            raise ValueError("unknown setting " + name)
        merged[name] = line[at + 1:]
    return merged
