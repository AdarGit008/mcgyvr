def sort_key(name: str) -> str:
    """The key a list of names is ordered by."""
    parts = name.split(" ", 1)
    if len(parts) == 1:
        return name.lower()
    return (parts[1] + " " + parts[0]).lower()
