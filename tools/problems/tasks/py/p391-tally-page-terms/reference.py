def tally_page_terms(entries: list[str], skips: list[str]) -> dict[str, int]:
    if not isinstance(entries, list) or not isinstance(skips, list):
        raise ValueError("entries and skips must both be lists")
    tally: dict[str, int] = {}
    for entry in entries:
        if not isinstance(entry, str) or entry == "":
            raise ValueError("every entry must be a non-empty string")
        head = entry.lower()
        if head.endswith("s") and len(head) > 4:
            head = head[:-1]
        if head in skips:
            continue
        tally[head] = tally.get(head, 0) + 1
    return tally
