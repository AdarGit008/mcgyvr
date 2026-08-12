def top_keys(counts: dict) -> list:
    if not counts:
        return []
    best = max(counts.values())
    return sorted(name for name in counts if counts[name] == best)
