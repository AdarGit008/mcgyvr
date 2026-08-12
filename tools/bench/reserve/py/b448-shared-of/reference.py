def in_both(entry: str, left: list, right: list) -> bool:
    return entry in left and entry in right


def shared_of(left: list, right: list) -> list:
    shared = []
    for entry in left:
        if in_both(entry, left, right) and entry not in shared:
            shared.append(entry)
    return shared
