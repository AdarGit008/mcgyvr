def flatten(nested: list) -> list:
    """Flatten arbitrarily nested lists; non-list values stay atomic."""
    flat: list = []
    stack = [iter(nested)]
    while stack:
        for item in stack[-1]:
            if isinstance(item, list):
                stack.append(iter(item))
                break
            flat.append(item)
        else:
            stack.pop()
    return flat
