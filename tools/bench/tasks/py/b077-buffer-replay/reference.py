def replay_buffer(ops, capacity):
    if isinstance(capacity, bool) or not isinstance(capacity, int) or capacity <= 0:
        raise ValueError("capacity must be a positive integer")
    held = []
    taken = []
    for op in ops:
        if op == "take":
            if not held:
                raise ValueError("take on an empty buffer")
            taken.append(held.pop(0))
        elif op.startswith("add:"):
            if len(held) == capacity:
                raise ValueError("buffer is full")
            held.append(op[4:])
        else:
            raise ValueError(f"unknown operation: {op}")
    return {"held": held, "taken": taken}
