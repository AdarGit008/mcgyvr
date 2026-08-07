def safe_divide(a, b) -> float | None:
    """Divide a by b; None on zero divisor, TypeError on non-numbers."""
    for value in (a, b):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(f"expected int or float, got {type(value).__name__}")
    if b == 0:
        return None
    return a / b
