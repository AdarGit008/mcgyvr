def gapped_match(needle: str, haystack: str, gap: int) -> bool:
    if not isinstance(needle, str) or needle == "":
        raise ValueError("needle must be a non-empty string")
    if isinstance(gap, bool) or not isinstance(gap, int) or gap < 0:
        raise ValueError("gap must be a non-negative whole number")

    memo: dict[tuple[int, int], bool] = {}

    def can(i: int, j: int) -> bool:
        if haystack[j] != needle[i]:
            return False
        if i == len(needle) - 1:
            return True
        if (i, j) in memo:
            return memo[i, j]
        limit = min(j + 1 + gap, len(haystack) - 1)
        result = any(can(i + 1, k) for k in range(j + 1, limit + 1))
        memo[i, j] = result
        return result

    return any(can(0, j) for j in range(len(haystack)))
