def raw_tally(recipes, item, batches):
    if not isinstance(item, str) or not item:
        raise ValueError("item must be a non-empty string")
    if isinstance(batches, bool) or not isinstance(batches, int) or batches < 1:
        raise ValueError("batches must be a positive integer")
    memo = {}
    visiting = set()

    def expand(name):
        if not isinstance(name, str) or not name:
            raise ValueError("component names must be non-empty strings")
        if name in memo:
            return memo[name]
        if name in visiting:
            raise ValueError("recipe cycle at " + name)
        if name not in recipes:
            return {name: 1}
        parts = recipes[name]
        if not isinstance(parts, list) or not parts:
            raise ValueError("a recipe must list at least one component")
        visiting.add(name)
        tally = {}
        for part in parts:
            sub = expand(part)
            for raw, units in sub.items():
                tally[raw] = tally.get(raw, 0) + units
        visiting.discard(name)
        memo[name] = tally
        return tally

    scaled = {}
    for raw, units in expand(item).items():
        scaled[raw] = units * batches
    return scaled
