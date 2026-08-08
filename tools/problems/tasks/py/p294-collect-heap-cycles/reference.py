from collections import deque


def collect_heap_cycles(heap: list[dict], held: list[list[str]]) -> list[dict]:
    if not isinstance(heap, list):
        raise ValueError("collect_heap_cycles expects a heap list")
    if not isinstance(held, list):
        raise ValueError("collect_heap_cycles expects a list of held-id lists")
    order: list[str] = []
    cells: dict[str, dict] = {}
    for entry in heap:
        if not isinstance(entry, dict):
            raise ValueError("every heap entry must be a cell")
        if not isinstance(entry.get("id"), str):
            raise ValueError("a cell needs a string id")
        if not isinstance(entry.get("refs"), list) or not isinstance(
            entry.get("finalizer"), bool
        ):
            raise ValueError(f"a cell needs refs and a boolean finalizer: {entry}")
        if entry["id"] in cells:
            raise ValueError(f"two cells carry the id {entry['id']}")
        cells[entry["id"]] = entry
        order.append(entry["id"])
    for entry in heap:
        for ref in entry["refs"]:
            if ref not in cells:
                raise ValueError(f"ref names no cell: {ref}")

    present = set(order)

    def reach(seeds: list[str]) -> set[str]:
        painted: set[str] = set()
        queue: deque[str] = deque()
        for seed in seeds:
            if seed in present and seed not in painted:
                painted.add(seed)
                queue.append(seed)
        while queue:
            here = queue.popleft()
            for ref in cells[here]["refs"]:
                if ref in present and ref not in painted:
                    painted.add(ref)
                    queue.append(ref)
        return painted

    burnt: set[str] = set()
    reports: list[dict] = []
    for roots in held:
        if not isinstance(roots, list):
            raise ValueError("every collection needs a held-id list")
        for name in roots:
            if not isinstance(name, str) or name not in cells:
                raise ValueError(f"held id names no cell: {name}")
            if name not in present:
                raise ValueError(f"held id was already swept: {name}")
        live = reach(roots)
        doomed = [name for name in order if name in present and name not in live]
        finalized = [
            name for name in doomed if cells[name]["finalizer"] and name not in burnt
        ]
        burnt.update(finalized)
        spared = reach(finalized)
        collected = [name for name in doomed if name not in spared]
        present.difference_update(collected)
        reports.append({"finalized": finalized, "collected": collected})
    return reports
