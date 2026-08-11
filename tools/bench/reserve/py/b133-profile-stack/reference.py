"""Resolve layered configuration profiles that extend one another."""


def merge_layers(base, override):
    """Deep-merge two nested mappings into a fresh mapping."""
    if not isinstance(base, dict) or not isinstance(override, dict):
        raise ValueError("merge_layers expects two mappings")
    merged = {}
    for key, value in base.items():
        merged[key] = value
    for key, theirs in override.items():
        ours = merged.get(key)
        if isinstance(ours, dict) and isinstance(theirs, dict):
            merged[key] = merge_layers(ours, theirs)
        else:
            merged[key] = theirs
    return merged


def resolve_profile(name, profiles):
    """Resolve a named profile through its extends chain."""
    if not isinstance(profiles, dict):
        raise ValueError("profiles must be a mapping")

    def resolve(target, trail):
        if target in trail:
            raise ValueError(f"extends cycle at: {target}")
        if target not in profiles:
            raise ValueError(f"unknown profile: {target}")
        profile = profiles[target]
        if not isinstance(profile, dict):
            raise ValueError(f"profile is not a mapping: {target}")
        parents = profile.get("extends", [])
        if not isinstance(parents, list):
            raise ValueError(f"extends must be a list: {target}")
        settings = profile.get("settings", {})
        if not isinstance(settings, dict):
            raise ValueError(f"settings must be a mapping: {target}")
        resolved = {}
        for parent in parents:
            if not isinstance(parent, str):
                raise ValueError(f"extends entries must be strings: {target}")
            resolved = merge_layers(resolved, resolve(parent, trail + [target]))
        return merge_layers(resolved, settings)

    return resolve(name, [])
