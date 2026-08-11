def pack_dials(dials):
    if not isinstance(dials, dict):
        raise ValueError("pack_dials expects a plain mapping")
    parts = []
    for name in sorted(dials):
        if name == "" or "=" in name or ";" in name:
            raise ValueError("bad dial name")
        position = dials[name]
        if isinstance(position, bool) or not isinstance(position, int) or position < 0:
            raise ValueError("bad dial position")
        parts.append(name + "=" + str(position))
    return ";".join(parts)
