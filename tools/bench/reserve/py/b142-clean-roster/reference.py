def clean_roster(names):
    if not isinstance(names, list):
        raise ValueError("clean_roster expects a list of names")
    seen = set()
    kept = []
    for raw in names:
        if not isinstance(raw, str):
            raise ValueError("every entry must be a string")
        name = " ".join(raw.split())
        if not name:
            raise ValueError("an entry may not be blank")
        if name.lower() not in seen:
            seen.add(name.lower())
            kept.append(name)
    return kept
