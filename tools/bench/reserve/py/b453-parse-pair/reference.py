def split_once(line: str) -> list:
    cut = line.find(":")
    if cut == -1:
        raise ValueError("a pair needs a colon")
    return [line[:cut], line[cut + 1 :]]


def parse_pair(line: str) -> list:
    parts = split_once(line)
    return [parts[0].strip(), parts[1].strip()]
