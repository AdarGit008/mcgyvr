ALLOWED = {"sku", "count", "note"}


def check_manifest(line: dict) -> dict:
    if set(line) - ALLOWED:
        raise ValueError("a manifest line carries sku, count and note only")
    sku, count = line.get("sku"), line.get("count")
    note = line.get("note", "")
    if not isinstance(sku, str) or sku.strip() == "":
        raise ValueError("the sku must be a non-empty string")
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise ValueError("the count must be a positive whole number")
    if not isinstance(note, str):
        raise ValueError("the note must be a string")
    return {"sku": sku.strip().upper(), "count": count, "note": note}
