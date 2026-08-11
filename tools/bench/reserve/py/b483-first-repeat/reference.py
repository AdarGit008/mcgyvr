def first_repeat(entries: list[str]) -> str:
    seen = set()
    for entry in entries:
        if entry in seen:
            return entry
        seen.add(entry)
    return ""
