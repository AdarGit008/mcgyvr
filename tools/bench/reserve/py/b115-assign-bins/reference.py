def assign_bins(rules, items):
    def matches(item, pattern):
        star = pattern.find("*")
        if star == -1:
            return item == pattern
        head, tail = pattern[:star], pattern[star + 1 :]
        return (
            len(item) >= len(head) + len(tail)
            and item.startswith(head)
            and item.endswith(tail)
        )

    if not isinstance(rules, list):
        raise ValueError("rules must be a list")
    bins = {}
    for rule in rules:
        if not isinstance(rule, list) or len(rule) != 2:
            raise ValueError("a rule is a [name, patterns] pair")
        name, patterns = rule
        if not isinstance(name, str) or name == "":
            raise ValueError("rule names must be non-empty strings")
        if name in bins:
            raise ValueError("rule names must not repeat")
        if not isinstance(patterns, list) or not patterns:
            raise ValueError("patterns must be a non-empty list")
        for pattern in patterns:
            if not isinstance(pattern, str) or pattern == "":
                raise ValueError("patterns must be non-empty strings")
            if pattern.count("*") > 1:
                raise ValueError("a pattern holds at most one star")
        bins[name] = []
    if not isinstance(items, list) or any(not isinstance(i, str) for i in items):
        raise ValueError("items must be a list of strings")
    leftover = []
    for item in items:
        placed = False
        for name, patterns in rules:
            if any(matches(item, pattern) for pattern in patterns):
                bins[name].append(item)
                placed = True
                break
        if not placed:
            leftover.append(item)
    return {"bins": bins, "leftover": leftover}
