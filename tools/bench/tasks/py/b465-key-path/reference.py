def key_path(store: dict, head: str) -> list:
    found = []
    lead = head + "."
    for key in store:
        if key.startswith(lead):
            rest = key[len(lead) :]
            if "." not in rest:
                found.append(rest)
    return found
