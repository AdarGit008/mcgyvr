def index_map(labels: list) -> dict:
    found = {}
    for i, label in enumerate(labels):
        if label not in found:
            found[label] = []
        found[label].append(i)
    return found
