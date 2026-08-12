def nest_get(tree: dict, path: list) -> str:
    """What a path of keys finds in nested mappings."""
    here = tree
    for key in path:
        if not isinstance(here, dict):
            return ""
        here = here.get(key)
    return here if isinstance(here, str) else ""
