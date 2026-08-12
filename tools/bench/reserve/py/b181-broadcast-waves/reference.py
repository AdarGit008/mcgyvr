def broadcast_waves(links, start):
    """Report a bulletin's spread through the desks, one wave per hop."""
    onward = {}
    for link in links:
        parts = link.split(">")
        if len(parts) != 2 or parts[0] == "" or parts[1] == "":
            raise ValueError("a link must be written sender>receiver")
        onward.setdefault(parts[0], []).append(parts[1])
    held = {start}
    lines = []
    wave = [start]
    while wave:
        lines.append(", ".join(wave))
        reached = []
        for desk in wave:
            for target in onward.get(desk, []):
                if target not in held:
                    held.add(target)
                    reached.append(target)
        wave = sorted(reached)
    return "\n".join(lines)
