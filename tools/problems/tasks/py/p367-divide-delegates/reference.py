"""Delegates handed to each slate by quota, leftover and roster."""


def _whole(value):
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def divide_delegates(slates: list, delegates: int) -> dict:
    if not isinstance(slates, list) or not slates:
        raise ValueError("there must be at least one slate")
    if not _whole(delegates):
        raise ValueError("the delegate count must be a whole number above zero")

    rows = []
    names = set()
    for raw in slates:
        if not isinstance(raw, dict):
            raise ValueError("a slate must be a mapping")
        name = raw.get("name")
        if not isinstance(name, str) or name == "":
            raise ValueError("a slate needs a non-empty name")
        if name in names:
            raise ValueError("two slates carry the same name")
        names.add(name)
        if not _whole(raw.get("votes")) or not _whole(raw.get("roster")):
            raise ValueError("votes and roster must be whole numbers above zero")
        rows.append(
            {"name": name, "votes": raw["votes"], "roster": raw["roster"]}
        )
    if sum(row["roster"] for row in rows) < delegates:
        raise ValueError("the rosters cannot hold that many delegates")

    held = {}
    standing = list(rows)
    left = delegates
    while standing:
        total = sum(row["votes"] for row in standing)
        share = []
        for at, row in enumerate(standing):
            exact = row["votes"] * left
            base = exact // total
            share.append(
                {"row": row, "at": at, "base": base, "rest": exact - base * total}
            )
        spare = left - sum(item["base"] for item in share)
        queue = sorted(
            share,
            key=lambda item: (-item["rest"], -item["row"]["votes"], item["at"]),
        )
        for item in queue:
            if spare == 0:
                break
            item["base"] += 1
            spare -= 1
        over = [item for item in share if item["base"] > item["row"]["roster"]]
        if not over:
            for item in share:
                held[item["row"]["name"]] = item["base"]
            break
        pinned = set()
        for item in over:
            held[item["row"]["name"]] = item["row"]["roster"]
            left -= item["row"]["roster"]
            pinned.add(item["row"]["name"])
        standing = [row for row in standing if row["name"] not in pinned]

    return {row["name"]: held[row["name"]] for row in rows}
