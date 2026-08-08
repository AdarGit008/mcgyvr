"""The snapshots to load to rebuild one wanted image."""


def order_snapshot_load(archive: list, wanted: str) -> dict:
    if not isinstance(archive, list):
        raise ValueError("the archive must be a list")
    by_name = {}
    for entry in archive:
        if not isinstance(entry, dict):
            raise ValueError("each snapshot is a record")
        if "name" not in entry or "parent" not in entry:
            raise ValueError("a snapshot needs both name and parent")
        if not isinstance(entry["name"], str) or entry["name"] == "":
            raise ValueError("name must be a non-empty string")
        if not isinstance(entry["parent"], str):
            raise ValueError("parent must be a string")
        if entry["name"] in by_name:
            raise ValueError("two snapshots share a name")
        by_name[entry["name"]] = entry
    if not isinstance(wanted, str) or wanted == "":
        raise ValueError("the wanted snapshot must be a non-empty string")
    order = []
    seen = set()
    at = wanted
    while True:
        if at not in by_name:
            return {"found": "no", "order": [], "why": "unknown"}
        if at in seen:
            return {"found": "no", "order": [], "why": "cycle"}
        seen.add(at)
        order.append(at)
        parent = by_name[at]["parent"]
        if parent == "":
            order.reverse()
            return {"found": "yes", "order": order, "why": ""}
        at = parent
