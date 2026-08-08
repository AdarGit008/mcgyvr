def kth_distinct(values: list[int], k: int) -> int:
    if not isinstance(values, list) or any(
        not isinstance(v, int) or isinstance(v, bool) for v in values
    ):
        raise ValueError("values must be a list of integers")
    if not values:
        raise ValueError("values must not be empty")
    if not isinstance(k, int) or isinstance(k, bool) or k < 1:
        raise ValueError("k must be a positive integer")
    distinct = sorted(set(values))
    if k > len(distinct):
        raise ValueError("k exceeds the number of distinct values")
    return distinct[k - 1]
