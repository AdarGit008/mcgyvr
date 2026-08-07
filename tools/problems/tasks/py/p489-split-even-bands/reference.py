def _whole(value, least):
    return isinstance(value, int) and not isinstance(value, bool) and value >= least


def split_even_bands(entries: list, bands: int) -> list:
    if not isinstance(entries, list) or len(entries) == 0:
        raise ValueError("entries must be a list holding at least one entry")
    seen = set()
    held = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("each entry must be a record")
        who = entry.get("who")
        if not isinstance(who, str) or who == "":
            raise ValueError("who must be a non-empty string")
        if who in seen:
            raise ValueError(f"two entries answer to {who}")
        seen.add(who)
        if not _whole(entry.get("mark"), 0):
            raise ValueError("mark must be a whole number of nought or more")
        held.append((who, entry["mark"]))
    if not _whole(bands, 1) or bands > len(held):
        raise ValueError("bands must be a whole number from one up to the entry count")

    seated = sorted(held, key=lambda member: (-member[1], member[0]))
    lowest = {}
    for seat, member in enumerate(seated):
        band = (seat * bands) // len(seated) + 1
        mark = member[1]
        if mark not in lowest or band < lowest[mark]:
            lowest[mark] = band

    return [{"who": who, "band": lowest[mark]} for who, mark in held]
