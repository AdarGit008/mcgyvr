def factorial(n: int) -> int:
    """Return n! for non-negative n."""
    if n < 0:
        raise ValueError(f"n must be non-negative, got {n}")
    if n == 0:
        return 1
    return n * factorial(n - 1)
