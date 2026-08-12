"""The options a tool runs with, settled from defaults, file and flags."""


def settle_options(defaults: dict, file_values: dict,
                   flag_values: dict, locked: list) -> dict:
    if not isinstance(locked, list) or any(not isinstance(k, str) for k in locked):
        raise ValueError("locked must be a list of strings")
    for source in (defaults, file_values, flag_values):
        if not isinstance(source, dict):
            raise ValueError("each source must be a flat mapping")
        for value in source.values():
            if not isinstance(value, str):
                raise ValueError("option values must be strings")
    settled = {}
    for key, value in defaults.items():
        settled[key] = value
    for key, value in file_values.items():
        settled[key] = value
    for key, value in flag_values.items():
        if key in locked:
            raise ValueError("locked key cannot be set by a flag: " + key)
        settled[key] = value
    return settled
