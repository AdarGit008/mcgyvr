def _whole(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def explode_bill_of_materials(parts: list[dict], root: str, batch: int) -> list[dict]:
    if not isinstance(parts, list):
        raise ValueError("parts must be a list")
    if not isinstance(root, str) or not root:
        raise ValueError("root must be a non-empty string")
    if not _whole(batch) or batch < 1:
        raise ValueError("batch must be an integer of at least 1")

    index: dict[str, list] = {}
    for entry in parts:
        if not isinstance(entry, dict):
            raise ValueError("a parts entry must be a record")
        name = entry.get("part")
        if not isinstance(name, str) or not name:
            raise ValueError("a part name must be a non-empty string")
        if name in index:
            raise ValueError(f"parts names the same part twice: {name}")
        uses = entry.get("uses")
        if not isinstance(uses, list) or not uses:
            raise ValueError(f"uses must be a non-empty list: {name}")
        here: set[str] = set()
        for use in uses:
            if not isinstance(use, dict):
                raise ValueError("a uses entry must be a record")
            sub = use.get("part")
            if not isinstance(sub, str) or not sub:
                raise ValueError("a sub-part name must be a non-empty string")
            if sub in here:
                raise ValueError(f"{name} names {sub} twice")
            here.add(sub)
            per = use.get("per")
            if not _whole(per) or per < 1:
                raise ValueError(f"per must be an integer of at least 1: {sub}")
        index[name] = uses

    totals: dict[str, int] = {}
    chain: set[str] = set()

    def explode(name: str, many: int) -> None:
        uses = index.get(name)
        if uses is None:
            totals[name] = totals.get(name, 0) + many
            return
        if name in chain:
            raise ValueError(f"the build loops through {name}")
        chain.add(name)
        for use in uses:
            explode(use["part"], many * use["per"])
        chain.discard(name)

    explode(root, batch)
    return [{"part": name, "count": totals[name]} for name in sorted(totals)]
