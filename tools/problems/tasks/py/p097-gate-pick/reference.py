import re

CLAUSE = re.compile(r"(0|[1-9]\d*)?:(0|[1-9]\d*)?((?:\^(?:0|[1-9]\d*))*)")


def pick_build(gate: str, offers: list[int]) -> int:
    if not isinstance(gate, str):
        raise ValueError("gate must be a string")
    clauses = []
    for part in gate.split(","):
        m = CLAUSE.fullmatch(part)
        if m is None:
            raise ValueError(f"malformed clause: {part}")
        lo = None if m.group(1) is None else int(m.group(1))
        hi = None if m.group(2) is None else int(m.group(2))
        if lo is not None and hi is not None and lo > hi:
            raise ValueError(f"ends out of order: {part}")
        out = set()
        carved_list = [int(n) for n in m.group(3)[1:].split("^")] if m.group(3) else []
        for carved in carved_list:
            if (lo is not None and carved < lo) or (hi is not None and carved > hi):
                raise ValueError(f"carve-out not covered by its clause: {part}")
            out.add(carved)
        clauses.append((lo, hi, out))
    for offer in offers:
        if not isinstance(offer, int) or isinstance(offer, bool) or offer < 0:
            raise ValueError("offers must be non-negative integers")
    best = -1
    for offer in offers:
        admitted = any(
            (lo is None or offer >= lo)
            and (hi is None or offer <= hi)
            and offer not in out
            for lo, hi, out in clauses
        )
        if admitted and offer > best:
            best = offer
    return best
