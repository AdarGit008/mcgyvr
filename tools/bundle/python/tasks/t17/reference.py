def greet(name: str, greeting: str = "Hello") -> str:
    """Format a greeting."""
    return greeting + ", " + name + "!"


def total_length(strings: list[str]) -> int:
    """Sum of the lengths of all strings."""
    return sum(len(s) for s in strings)
