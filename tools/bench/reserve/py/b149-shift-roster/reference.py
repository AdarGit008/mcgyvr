def shift_roster(entries):
    if not isinstance(entries, list):
        raise ValueError("entries must be a list")
    roster, seen = {}, set()
    for entry in entries:
        if not isinstance(entry, list) or len(entry) != 2:
            raise ValueError("each entry must be a [name, shift] pair")
        name, shift = entry
        if not all(isinstance(v, str) and v for v in (name, shift)):
            raise ValueError("names and shifts must be non-empty strings")
        if name in seen:
            raise ValueError("a name may appear in only one entry")
        seen.add(name)
        roster.setdefault(shift, []).append(name)
    return {shift: sorted(names) for shift, names in roster.items()}
