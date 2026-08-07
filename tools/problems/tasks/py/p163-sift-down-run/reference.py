def sift_down_run(heap: list[int], start: int) -> list[list[int]]:
    if not isinstance(heap, list) or not heap:
        raise ValueError("sift_down_run expects a non-empty array")
    for value in heap:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("every entry must be a whole number")
    if isinstance(start, bool) or not isinstance(start, int):
        raise ValueError("start slot must be a whole number")
    if start < 0 or start >= len(heap):
        raise ValueError("start slot is outside the array")
    array = list(heap)
    trail = [start]
    slot = start
    while True:
        left = 2 * slot + 1
        right = left + 1
        if left >= len(array):
            break
        pick = left
        if right < len(array) and array[right] < array[left]:
            pick = right
        if array[pick] >= array[slot]:
            break
        array[slot], array[pick] = array[pick], array[slot]
        slot = pick
        trail.append(slot)
    return [array, trail]
