STOPS = frozenset(".!?")


def split_prose_sentences(passage: str, abbreviations: list[str]) -> list[str]:
    if not isinstance(passage, str):
        raise ValueError("passage must be a string")
    if not isinstance(abbreviations, list):
        raise ValueError("abbreviations must be a list")
    for item in abbreviations:
        if not isinstance(item, str):
            raise ValueError("every abbreviation must be a string")
        if not item.endswith("."):
            raise ValueError("every abbreviation must end in a period")
        if " " in item:
            raise ValueError("an abbreviation may not hold a space")
    known = set(abbreviations)
    sentences: list[str] = []
    quoted = False
    depth = 0
    start = 0
    at = 0
    while at < len(passage):
        ch = passage[at]
        if ch == '"':
            quoted = not quoted
            at += 1
            continue
        if not quoted and ch == "(":
            depth += 1
            at += 1
            continue
        if not quoted and ch == ")":
            depth -= 1
            if depth < 0:
                raise ValueError("closing bracket with no opener")
            at += 1
            continue
        if not quoted and depth == 0 and ch in STOPS:
            last = at
            while last + 1 < len(passage) and passage[last + 1] in STOPS:
                last += 1
            after = last + 1
            if after < len(passage) and passage[after] != " ":
                at = after
                continue
            head = last
            while head > 0 and passage[head - 1] != " ":
                head -= 1
            if passage[head : last + 1] in known:
                at = after
                continue
            piece = passage[start:after].strip()
            if piece != "":
                sentences.append(piece)
            at = after
            start = after
            continue
        at += 1
    if depth != 0:
        raise ValueError("bracket left open")
    if quoted:
        raise ValueError("quotation left open")
    tail = passage[start:].strip()
    if tail != "":
        sentences.append(tail)
    return sentences
