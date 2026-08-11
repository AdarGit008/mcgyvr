def key_of(record: dict) -> str:
    return record.get("name", "")


def group_sum(records: list) -> dict:
    totals = {}
    for record in records:
        group = key_of(record)
        if group == "":
            continue
        totals[group] = totals.get(group, 0) + record.get("amount", 0)
    return totals
