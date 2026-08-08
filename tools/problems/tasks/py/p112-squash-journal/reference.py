def squash_journal(ops: list) -> list:
    value = {}
    born = {}

    def as_key(raw):
        if not isinstance(raw, str) or raw == "":
            raise ValueError("key must be a non-empty string")
        return raw

    for index, op in enumerate(ops):
        kind = op[0]
        if kind == "put":
            key = as_key(op[1])
            val = op[2]
            if not isinstance(val, int) or isinstance(val, bool) or val <= 0:
                raise ValueError("value must be a positive integer")
            value[key] = val
            born[key] = index
        elif kind == "del":
            key = as_key(op[1])
            if key not in value:
                raise ValueError("cannot delete an absent key")
            del value[key]
            del born[key]
        elif kind == "ren":
            src = as_key(op[1])
            dst = as_key(op[2])
            if src not in value:
                raise ValueError("cannot rename an absent key")
            if dst in value:
                raise ValueError("cannot rename onto an existing key")
            value[dst] = value.pop(src)
            born[dst] = born.pop(src)
        else:
            raise ValueError("unknown operation")

    return [
        ["put", key, value[key]]
        for key in sorted(value, key=lambda name: born[name])
    ]
