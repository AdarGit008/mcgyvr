"""Stock lookup across a storeroom's nested zones."""


def rack_units(bins, sku):
    if not isinstance(sku, str) or sku == "":
        raise ValueError("sku must be a non-empty string")
    if sku not in bins:
        return 0
    qty = bins[sku]
    if isinstance(qty, bool) or not isinstance(qty, int) or qty <= 0:
        raise ValueError("a recorded count must be a positive integer")
    return qty


def zone_stock(zone, sku):
    seen = set()
    holders = []

    def walk(node):
        if not isinstance(node, dict):
            raise ValueError("a zone must be a record")
        name = node.get("name")
        if not isinstance(name, str) or name == "":
            raise ValueError("a zone name must be a non-empty string")
        if name in seen:
            raise ValueError("zone names must be unique across the storeroom")
        seen.add(name)
        bins = node.get("bins")
        if not isinstance(bins, dict):
            raise ValueError("bins must be a mapping of sku to units")
        children = node.get("children")
        if not isinstance(children, list):
            raise ValueError("children must be a list of zones")
        units = rack_units(bins, sku)
        if units > 0:
            holders.append(name)
        for child in children:
            units += walk(child)
        return units

    return {"total": walk(zone), "holders": holders}
