def _pair(row, what):
    if not isinstance(row, list) or len(row) != 2:
        raise ValueError(f"every {what} is a pair of names")
    for name in row:
        if not isinstance(name, str) or name == "":
            raise ValueError(f"a {what} name must be a non-empty string")
    return row[0], row[1]


def lock_cycle_victim(holds: list[list], blocked: list[list]) -> dict:
    if not isinstance(holds, list) or not isinstance(blocked, list):
        raise ValueError("lock_cycle_victim expects two lists of pairs")
    holder = {}
    held = {}
    workers = []
    for row in holds:
        resource, worker = _pair(row, "granted lock")
        if resource in holder:
            raise ValueError(f"{resource} is granted twice")
        holder[resource] = worker
        held[worker] = held.get(worker, 0) + 1
        if worker not in workers:
            workers.append(worker)
    waiting_on = {}
    for row in blocked:
        worker, resource = _pair(row, "blocked request")
        if worker in waiting_on:
            raise ValueError(f"{worker} is blocked on two resources")
        if holder.get(resource) == worker:
            raise ValueError(f"{worker} is blocked on a lock it holds")
        waiting_on[worker] = resource
        if worker not in workers:
            workers.append(worker)

    def step(worker):
        resource = waiting_on.get(worker)
        if resource is None:
            return None
        return holder.get(resource)

    done = set()
    on_ring = set()
    for start in workers:
        if start in done:
            continue
        path = []
        seen_at = {}
        current = start
        while current is not None and current not in done and current not in seen_at:
            seen_at[current] = len(path)
            path.append(current)
            current = step(current)
        if current is not None and current in seen_at:
            for worker in path[seen_at[current]:]:
                on_ring.add(worker)
        done.update(path)

    if not on_ring:
        return {"victim": "", "cycle": []}
    victim = min(on_ring, key=lambda worker: (held.get(worker, 0), worker))
    cycle = [victim]
    current = step(victim)
    while current != victim:
        cycle.append(current)
        current = step(current)
    return {"victim": victim, "cycle": cycle}
