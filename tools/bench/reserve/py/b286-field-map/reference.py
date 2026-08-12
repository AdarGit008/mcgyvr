def field_map(entries: list) -> dict:
    settings = {}
    for entry in entries:
        if "=" not in entry:
            continue
        key, value = entry.split("=", 1)
        settings[key] = value
    return settings
