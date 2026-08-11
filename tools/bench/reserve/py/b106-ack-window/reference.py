def new_link(size):
    if isinstance(size, bool) or not isinstance(size, int) or size < 1:
        raise ValueError("size must be a positive integer")
    return {"size": size, "next": 0, "pending": [], "delivered": 0}


def link_send(link, payload):
    if not isinstance(payload, str) or not payload:
        raise ValueError("payload must be a non-empty string")
    if len(link["pending"]) == link["size"]:
        raise ValueError("the window is full")
    seq = link["next"]
    link["next"] += 1
    link["pending"].append([seq, payload])
    return seq


def link_ack(link, ack):
    if isinstance(ack, bool) or not isinstance(ack, int):
        raise ValueError("ack must be an integer")
    if ack < -1:
        raise ValueError("an ack below -1 names no frame")
    if ack >= link["next"]:
        raise ValueError("cannot acknowledge an unsent frame")
    freed = []
    kept = []
    for seq, payload in link["pending"]:
        if seq <= ack:
            freed.append(payload)
        else:
            kept.append([seq, payload])
    link["pending"] = kept
    link["delivered"] += len(freed)
    return freed
