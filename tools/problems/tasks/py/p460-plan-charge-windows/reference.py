def _whole(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def plan_charge_windows(windows: list, target: int) -> dict:
    if not isinstance(windows, list):
        raise ValueError("windows must be a list")
    if not _whole(target) or target < 0:
        raise ValueError("target must be a whole number of nought or more")

    labels: set[str] = set()
    bands: list[dict] = []
    for band in windows:
        if not isinstance(band, dict):
            raise ValueError("a window must be a record")
        label = band.get("label")
        if not isinstance(label, str) or not label:
            raise ValueError("a label must be a non-empty string")
        if label in labels:
            raise ValueError(f"two windows carry the label {label}")
        labels.add(label)
        opens = band.get("opens")
        if not _whole(opens) or opens < 0:
            raise ValueError("opens must be a whole number of nought or more")
        shuts = band.get("shuts")
        if not _whole(shuts) or shuts <= opens:
            raise ValueError("shuts must be a whole number later than opens")
        price = band.get("price")
        if not _whole(price) or price < 0:
            raise ValueError("price must be a whole number of nought or more")
        rate = band.get("rate")
        if not _whole(rate) or rate < 1:
            raise ValueError("rate must be a whole number above nought")
        if not isinstance(band.get("blocked"), bool):
            raise ValueError("blocked must be either true or false")
        bands.append(
            {
                "label": label,
                "opens": opens,
                "shuts": shuts,
                "price": price,
                "rate": rate,
                "blocked": band["blocked"],
            }
        )

    by_clock = sorted(bands, key=lambda band: band["opens"])
    for earlier, later in zip(by_clock, by_clock[1:]):
        if earlier["shuts"] > later["opens"]:
            raise ValueError(f"the windows {earlier['label']} and {later['label']} overlap")

    by_price = sorted(bands, key=lambda band: (band["price"], band["opens"]))
    taken: dict[str, int] = {}
    owed = target
    cost = 0
    for band in by_price:
        if owed == 0:
            break
        if band["blocked"]:
            continue
        room = (band["shuts"] - band["opens"]) * band["rate"]
        units = min(room, owed)
        if units == 0:
            continue
        taken[band["label"]] = units
        cost += units * band["price"]
        owed -= units

    plan = [[band["label"], taken[band["label"]]] for band in by_clock if band["label"] in taken]
    return {"plan": plan, "cost": cost, "short": owed}
