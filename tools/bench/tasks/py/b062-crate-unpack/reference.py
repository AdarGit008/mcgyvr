"""Unpack a nested crate of item names into a flat picking list."""


def unpack_crates(crate: list) -> list:
    names = []
    for entry in crate:
        if isinstance(entry, list):
            names.extend(unpack_crates(entry))
        elif isinstance(entry, str) and entry:
            names.append(entry)
        else:
            raise ValueError("crate entries are item names or nested crates")
    return names


def crate_depth(crate: list) -> int:
    depth = 1
    for entry in crate:
        if isinstance(entry, list):
            depth = max(depth, 1 + crate_depth(entry))
    return depth
