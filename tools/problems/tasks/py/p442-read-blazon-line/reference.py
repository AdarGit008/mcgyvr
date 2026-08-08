TINCTURES = frozenset(
    {"or", "argent", "gules", "azure", "sable", "vert", "purpure"}
)

COUNTS = {"a": 1, "two": 2, "three": 3, "four": 4, "five": 5}

CHARGES = frozenset({"lion", "mullet", "crescent", "rose", "bend"})


def _tincture(word: str) -> str:
    if word not in TINCTURES:
        raise ValueError(f"unknown tincture {word}")
    return word


def read_blazon_line(line: str) -> dict:
    if not isinstance(line, str):
        raise ValueError("blazon line must be a string")
    if line == "":
        raise ValueError("blazon line is empty")
    clauses = line.split("; ")
    for clause in clauses:
        if clause == "":
            raise ValueError("blazon line has an empty clause")

    head = clauses[0].split(" ")
    if len(head) == 1:
        field = {"cut": "plain", "tinctures": [_tincture(head[0])]}
    elif len(head) == 5:
        if head[0] != "parted" or head[3] != "and":
            raise ValueError("malformed field clause")
        if head[1] not in ("pale", "fess"):
            raise ValueError(f"unknown division {head[1]}")
        left = _tincture(head[2])
        right = _tincture(head[4])
        if left == right:
            raise ValueError("a parted field needs two different tinctures")
        field = {"cut": head[1], "tinctures": [left, right]}
    else:
        raise ValueError("malformed field clause")

    charges = []
    named = set()
    for clause in clauses[1:]:
        words = clause.split(" ")
        if len(words) != 3:
            raise ValueError("a charge clause is three words")
        if words[0] not in COUNTS:
            raise ValueError(f"unknown count {words[0]}")
        count = COUNTS[words[0]]
        bare = words[1]
        if count > 1:
            if not bare.endswith("s"):
                raise ValueError("a count above one needs the plural word")
            bare = bare[:-1]
        if bare not in CHARGES:
            raise ValueError(f"unknown charge word {words[1]}")
        if bare in named:
            raise ValueError(f"charge word {bare} is named twice")
        named.add(bare)
        charges.append(
            {"count": count, "charge": bare, "tincture": _tincture(words[2])}
        )

    return {"field": field, "charges": charges}
