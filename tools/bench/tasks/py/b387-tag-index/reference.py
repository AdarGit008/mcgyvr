def tags_of(line) -> list:
    if not isinstance(line, str):
        raise ValueError("a line must be text")
    return [tag.strip() for tag in line.split(",") if tag.strip()]


def tag_index(lines: list) -> dict:
    index = {}
    for line in lines:
        for tag in tags_of(line):
            if tag not in index:
                index[tag] = []
            index[tag].append(line)
    return index
