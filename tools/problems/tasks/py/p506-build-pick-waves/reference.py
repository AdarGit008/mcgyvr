import re

ZONE = re.compile(r"[a-f]")


def _whole(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def build_pick_waves(orders, limits: dict) -> dict:
    if not isinstance(limits, dict):
        raise ValueError("the limits must be a mapping")
    for key in ("lines", "orders", "zones"):
        if not _whole(limits.get(key)):
            raise ValueError("every limit must be a positive whole number")
    line_cap = limits["lines"]
    order_cap = limits["orders"]
    zone_cap = limits["zones"]
    if not isinstance(orders, list):
        raise ValueError("the orders must be a list")

    refs = set()
    parsed = []
    for order in orders:
        if not isinstance(order, dict):
            raise ValueError("an order must be a mapping")
        ref = order.get("ref")
        if not isinstance(ref, str) or not ref:
            raise ValueError("an order needs a non-empty ref")
        if ref in refs:
            raise ValueError("two orders carry the same ref")
        refs.add(ref)
        lines = order.get("lines")
        if not _whole(lines):
            raise ValueError("lines must be a positive whole number")
        zones = order.get("zones")
        if not isinstance(zones, list) or not zones:
            raise ValueError("an order needs a non-empty list of zones")
        kept = []
        for zone in zones:
            if not isinstance(zone, str) or ZONE.fullmatch(zone) is None:
                raise ValueError("a zone must be one letter from a to f")
            if zone in kept:
                raise ValueError("an order repeats a zone")
            kept.append(zone)
        parsed.append((ref, lines, kept))

    waves = []
    refused = []
    open_wave = None
    for ref, lines, zones in parsed:
        if lines > line_cap or len(zones) > zone_cap:
            refused.append(ref)
            continue
        if open_wave is not None:
            merged = set(open_wave["zones"]) | set(zones)
            fits = (
                open_wave["lines"] + lines <= line_cap
                and len(open_wave["refs"]) < order_cap
                and len(merged) <= zone_cap
            )
            if fits:
                open_wave["refs"].append(ref)
                open_wave["lines"] += lines
                open_wave["zones"] = sorted(merged)
                continue
        open_wave = {
            "name": "w" + str(len(waves) + 1),
            "refs": [ref],
            "lines": lines,
            "zones": sorted(zones),
        }
        waves.append(open_wave)

    return {"waves": waves, "refused": refused}
