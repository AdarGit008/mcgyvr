def _whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def reorder_quantities(lines: list) -> list:
    if not isinstance(lines, list):
        raise ValueError("reorder_quantities expects a list of lines")

    buys = []
    seen = set()
    for line in lines:
        if not isinstance(line, dict):
            raise ValueError("a line is not a mapping")
        if sorted(line) != ["due", "high", "low", "pack", "shelf", "sku"]:
            raise ValueError("a line's keys are not exactly the six named")
        sku = line["sku"]
        if not isinstance(sku, str) or sku == "":
            raise ValueError("an sku is not a non-empty string")
        if sku in seen:
            raise ValueError("an sku is repeated")
        seen.add(sku)
        counts = {}
        for field in ("shelf", "due", "low"):
            value = line[field]
            if not _whole(value) or value < 0:
                raise ValueError("a shelf, due or low is not whole or falls below nought")
            counts[field] = value
        high = line["high"]
        if not _whole(high) or high < counts["low"]:
            raise ValueError("a high is not whole or falls below the low")
        pack = line["pack"]
        if not _whole(pack) or pack < 1:
            raise ValueError("a pack is not whole or falls below one")

        cover = counts["shelf"] + counts["due"]
        if cover > counts["low"]:
            continue
        want = high - cover
        if want <= 0:
            continue
        buys.append({"sku": sku, "units": -(-want // pack) * pack})

    return buys
