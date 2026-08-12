def diff_paths(before, after):
    if not isinstance(before, dict) or not isinstance(after, dict):
        raise ValueError("both arguments must be mappings")
    paths = []
    for key in set(before) | set(after):
        va, vb = before.get(key), after.get(key)
        if not all(v is None or isinstance(v, (str, dict)) for v in (va, vb)):
            raise ValueError("every value must be a string or a mapping")
        if isinstance(va, dict) and isinstance(vb, dict):
            paths += [key + "/" + p for p in diff_paths(va, vb)]
        elif va != vb:
            paths.append(key)
    return sorted(paths)
