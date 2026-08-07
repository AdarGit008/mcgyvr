def fib(n: int) -> int:
    """n-th Fibonacci number, iteratively."""
    if n < 0:
        raise ValueError(f"n must be non-negative, got {n}")
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a
