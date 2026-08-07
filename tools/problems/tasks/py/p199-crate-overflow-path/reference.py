def _whole(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _check(raw) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("a crate must be a mapping")
    tag = raw.get("tag")
    if not isinstance(tag, str) or not tag:
        raise ValueError("a crate needs a non-empty tag")
    if "." in tag:
        raise ValueError("a tag may not carry a full stop: " + tag)
    if not _whole(raw.get("weight")) or raw["weight"] < 0:
        raise ValueError("a weight is a non-negative whole number")
    if not _whole(raw.get("cap")) or raw["cap"] <= 0:
        raise ValueError("a cap is a positive whole number")
    inside = raw.get("inside")
    if not isinstance(inside, list):
        raise ValueError("inside must be a list")
    tags = set()
    for packed in inside:
        child = _check(packed)
        if child["tag"] in tags:
            raise ValueError(
                "two crates packed side by side share the tag " + child["tag"]
            )
        tags.add(child["tag"])
    return raw


def _walk(crate: dict, trail: str) -> tuple:
    gross = crate["weight"]
    spill = ""
    for packed in crate["inside"]:
        below_gross, below_spill = _walk(packed, trail + "." + packed["tag"])
        gross += below_gross
        if not spill and below_spill:
            spill = below_spill
    if not spill and gross > crate["cap"]:
        spill = trail
    return (gross, spill)


def crate_overflow_path(root: dict) -> str:
    crate = _check(root)
    return _walk(crate, crate["tag"])[1]
