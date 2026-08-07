import re

CODE = re.compile(r"[A-Z]{3}-[0-9]{3}")
DEPOT = re.compile(r"[A-Z]{3}")


def _whole(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def sort_postal_items(codes: list[str], bins: list[dict]) -> list[str]:
    if not isinstance(bins, list) or not bins:
        raise ValueError("bins must be a non-empty list")
    seen: set[str] = set()
    for bin_ in bins:
        if not isinstance(bin_, dict):
            raise ValueError("a bin must be a record")
        name = bin_.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError("a bin name must be a non-empty string")
        if name in ("HOLD", "BAD"):
            raise ValueError(f"a bin may not take a mark for a name: {name}")
        if name in seen:
            raise ValueError(f"bin names repeat: {name}")
        seen.add(name)
        depot = bin_.get("depot")
        if not isinstance(depot, str) or DEPOT.fullmatch(depot) is None:
            raise ValueError("a bin depot must be three capital letters")
        low = bin_.get("low")
        if not _whole(low) or low < 0 or low > 999:
            raise ValueError("low must be an integer from 0 to 999")
        high = bin_.get("high")
        if not _whole(high) or high < 0 or high > 999:
            raise ValueError("high must be an integer from 0 to 999")
        if low > high:
            raise ValueError(f"low is above high in bin {name}")

    if not isinstance(codes, list):
        raise ValueError("codes must be a list of strings")
    for code in codes:
        if not isinstance(code, str):
            raise ValueError("codes must be a list of strings")

    routed: list[str] = []
    for code in codes:
        if CODE.fullmatch(code) is None:
            routed.append("BAD")
            continue
        depot = code[:3]
        walk = int(code[4:])
        landed = "HOLD"
        for bin_ in bins:
            if bin_["depot"] == depot and bin_["low"] <= walk <= bin_["high"]:
                landed = bin_["name"]
                break
        routed.append(landed)
    return routed
