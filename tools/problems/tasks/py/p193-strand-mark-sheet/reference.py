"""The term mark built from weighted strands with discards."""

import functools


def _whole(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _pieces(name: str, work) -> list:
    if not isinstance(work, list) or not work:
        raise ValueError("strand " + name + " carries no work")
    out = []
    for at, entry in enumerate(work):
        if not isinstance(entry, list) or len(entry) != 2:
            raise ValueError("a piece is a pair")
        raw, available = entry
        if not _whole(available) or available <= 0:
            raise ValueError("a piece must be available for a positive count")
        if raw == "absent":
            score = 0
        elif _whole(raw):
            score = raw
            if score < 0:
                raise ValueError("a score cannot be negative")
            if score > available:
                raise ValueError("a score cannot exceed its availability")
        else:
            raise ValueError("a score is a whole number or the word absent")
        out.append({"score": score, "available": available, "at": at})
    return out


def _weakest_first(a: dict, b: dict) -> int:
    left = a["score"] * b["available"]
    right = b["score"] * a["available"]
    if left != right:
        return left - right
    if a["available"] != b["available"]:
        return b["available"] - a["available"]
    return a["at"] - b["at"]


def strand_mark_sheet(strands: list) -> dict:
    if not isinstance(strands, list) or not strands:
        raise ValueError("the report holds no strands")
    names = set()
    discarded = []
    shares = 0
    mark = 0
    for strand in strands:
        if not isinstance(strand, dict):
            raise ValueError("a strand must be a mapping")
        name = strand.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError("a strand needs a non-empty name")
        if name in names:
            raise ValueError("repeated strand name: " + name)
        names.add(name)
        share = strand.get("share")
        if not _whole(share) or share < 0:
            raise ValueError("a share is a non-negative whole number")
        shares += share
        discard = strand.get("discard")
        if not _whole(discard) or discard < 0:
            raise ValueError("a discard count is a non-negative whole number")
        ranked = _pieces(name, strand.get("work"))
        order = sorted(ranked, key=functools.cmp_to_key(_weakest_first))
        count = min(discard, len(ranked) - 1)
        gone = set()
        for piece in order[:count]:
            gone.add(piece["at"])
            discarded.append(name + "#" + str(piece["at"]))
        scored = 0
        available = 0
        for piece in ranked:
            if piece["at"] in gone:
                continue
            scored += piece["score"]
            available += piece["available"]
        mark += share * scored // available
    if shares != 1000:
        raise ValueError("shares come to " + str(shares) + ", not 1000")
    return {"mark": mark, "discarded": discarded}
