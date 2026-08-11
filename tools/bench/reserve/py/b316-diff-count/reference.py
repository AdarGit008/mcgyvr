def diff_count(left: list, right: list) -> int:
    differences = abs(len(left) - len(right))
    for i in range(min(len(left), len(right))):
        if left[i] != right[i]:
            differences += 1
    return differences
