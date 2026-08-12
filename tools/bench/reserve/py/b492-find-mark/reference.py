def find_mark(ordered: list[int], mark: int) -> int:
    low = 0
    high = len(ordered) - 1
    while low <= high:
        mid = (low + high) // 2
        if ordered[mid] == mark:
            return mid
        if ordered[mid] < mark:
            low = mid + 1
        else:
            high = mid - 1
    return -1
