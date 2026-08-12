def row_key(name: str) -> str:
    return name[0].upper()


def index_rows(names: list) -> dict:
    index = {}
    for name in names:
        key = row_key(name)
        if key not in index:
            index[key] = []
        index[key].append(name)
    return index
