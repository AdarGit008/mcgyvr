"""Plan courier loads by halving a consignment until every load fits."""


def plan_batches(units, capacity):
    if isinstance(units, bool) or not isinstance(units, int) or units <= 0:
        raise ValueError("units must be a positive integer")
    if isinstance(capacity, bool) or not isinstance(capacity, int) or capacity <= 0:
        raise ValueError("capacity must be a positive integer")
    if units <= capacity:
        return {"loads": [units], "splits": 0, "rounds": 0}
    upper = (units + 1) // 2
    first = plan_batches(upper, capacity)
    second = plan_batches(units - upper, capacity)
    return {
        "loads": first["loads"] + second["loads"],
        "splits": 1 + first["splits"] + second["splits"],
        "rounds": 1 + max(first["rounds"], second["rounds"]),
    }
