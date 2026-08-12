def alternate_merge(left: list, right: list) -> list:
    merged = []
    for i in range(max(len(left), len(right))):
        if i < len(left):
            merged.append(left[i])
        if i < len(right):
            merged.append(right[i])
    return merged
