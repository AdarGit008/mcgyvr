def sift_marks(entries: list[str], mark: str) -> list[list[str]]:
    carrying = []
    plain = []
    for entry in entries:
        if entry.startswith(mark):
            carrying.append(entry)
        else:
            plain.append(entry)
    return [carrying, plain]
