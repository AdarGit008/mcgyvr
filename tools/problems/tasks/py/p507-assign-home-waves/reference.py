import re

LETTER = re.compile(r"[a-z]")


def assign_home_waves(waves, orders) -> dict:
    if not isinstance(waves, list) or not waves:
        raise ValueError("the waves must be a non-empty list")
    names = []
    homes = []
    caps = []
    for wave in waves:
        if not isinstance(wave, dict):
            raise ValueError("a wave must be a mapping")
        name = wave.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError("a wave needs a non-empty name")
        if name in names:
            raise ValueError("two waves carry the same name")
        home = wave.get("home")
        if not isinstance(home, str) or LETTER.fullmatch(home) is None:
            raise ValueError("a home must be one lowercase letter")
        if home in homes:
            raise ValueError("two waves keep the same home")
        cap = wave.get("cap")
        if not isinstance(cap, int) or isinstance(cap, bool) or cap <= 0:
            raise ValueError("a cap must be a positive whole number")
        names.append(name)
        homes.append(home)
        caps.append(cap)

    if not isinstance(orders, list):
        raise ValueError("the orders must be a list")
    refs = []
    touched = []
    for order in orders:
        if not isinstance(order, dict):
            raise ValueError("an order must be a mapping")
        ref = order.get("ref")
        if not isinstance(ref, str) or not ref:
            raise ValueError("an order needs a non-empty ref")
        if ref in refs:
            raise ValueError("two orders carry the same ref")
        zones = order.get("zones")
        if not isinstance(zones, list) or not zones:
            raise ValueError("an order needs a non-empty list of zones")
        kept = []
        for zone in zones:
            if not isinstance(zone, str) or LETTER.fullmatch(zone) is None:
                raise ValueError("a zone must be one lowercase letter")
            if zone in kept:
                raise ValueError("an order repeats a zone")
            kept.append(zone)
        refs.append(ref)
        touched.append(kept)

    held = [[] for _ in names]
    spill = []
    for index, ref in enumerate(refs):
        placed = -1
        for slot in range(len(names)):
            if homes[slot] in touched[index] and len(held[slot]) < caps[slot]:
                placed = slot
                break
        if placed < 0:
            spill.append(ref)
        else:
            held[placed].append(ref)

    return {
        "loads": [{"name": name, "refs": held[slot]} for slot, name in enumerate(names)],
        "spill": spill,
    }
