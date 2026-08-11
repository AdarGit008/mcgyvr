def carry_add(left: list[int], right: list[int]) -> list[int]:
    out = []
    carried = 0
    i = len(left) - 1
    j = len(right) - 1
    while i >= 0 or j >= 0 or carried > 0:
        a = left[i] if i >= 0 else 0
        b = right[j] if j >= 0 else 0
        total = a + b + carried
        out.insert(0, total % 10)
        carried = 1 if total >= 10 else 0
        i -= 1
        j -= 1
    return out
