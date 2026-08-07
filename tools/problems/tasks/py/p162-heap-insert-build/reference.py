def build_min_heap_by_insertion(values: list[int]) -> list[int]:
    if not isinstance(values, list):
        raise ValueError("build_min_heap_by_insertion expects a list")
    for value in values:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("every entry must be a whole number")
    heap: list[int] = []
    for value in values:
        heap.append(value)
        slot = len(heap) - 1
        while slot > 0:
            parent = (slot - 1) // 2
            if heap[parent] <= heap[slot]:
                break
            heap[parent], heap[slot] = heap[slot], heap[parent]
            slot = parent
    return heap
