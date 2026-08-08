def resolve_profile(profiles: dict, wanted: str) -> dict:
    chain: list[str] = []
    seen: set[str] = set()
    current: str | None = wanted
    while current is not None:
        if current not in profiles:
            raise ValueError(f"unknown profile {current}")
        if current in seen:
            raise ValueError(f"inheritance cycle at {current}")
        seen.add(current)
        chain.append(current)
        current = profiles[current].get("extends")
    resolved: dict = {}
    for label in reversed(chain):
        for key, value in profiles[label].items():
            if key != "extends":
                resolved[key] = value
    return resolved
