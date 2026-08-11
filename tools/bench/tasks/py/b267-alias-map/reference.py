def alias_resolve(aliases: dict, name: str) -> str:
    if name in aliases:
        return aliases[name]
    return name


def alias_names(aliases: dict) -> list:
    return sorted(aliases)
