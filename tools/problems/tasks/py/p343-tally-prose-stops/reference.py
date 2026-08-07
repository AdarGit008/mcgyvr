MARKS = frozenset(".!?")
LETTERS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")
DIGITS = frozenset("0123456789")
CAPITALS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZ")


def count_sentences(prose: str, titles: list[str]) -> int:
    if not isinstance(prose, str):
        raise ValueError("prose must be a string")
    if not isinstance(titles, list):
        raise ValueError("titles must be a list")
    for title in titles:
        if not isinstance(title, str) or title == "":
            raise ValueError("a title must be a non-empty string")
        if any(ch not in LETTERS for ch in title):
            raise ValueError("a title must be a run of letters")
    known = set(titles)
    endings = 0
    depth = 0
    aside = False
    at = 0
    tail_from = 0
    while at < len(prose):
        ch = prose[at]
        if ch == "'":
            aside = not aside
            at += 1
            continue
        if ch == "[":
            depth += 1
            at += 1
            continue
        if ch == "]":
            depth -= 1
            if depth < 0:
                raise ValueError("a square bracket was closed with no opener")
            at += 1
            continue
        if not aside and depth == 0 and ch in MARKS:
            last = at
            while last + 1 < len(prose) and prose[last + 1] in MARKS:
                last += 1
            after = last + 1
            inert = False
            if ch == "." and last == at:
                prev = at - 1
                if (
                    prev >= 0
                    and prose[prev] in DIGITS
                    and after < len(prose)
                    and prose[after] in DIGITS
                ):
                    inert = True
                head = at
                while head > 0 and prose[head - 1] in LETTERS:
                    head -= 1
                if head < at and prose[head:at] in known:
                    inert = True
                if (
                    prev >= 0
                    and prose[prev] in CAPITALS
                    and (prev == 0 or prose[prev - 1] == " ")
                ):
                    inert = True
            if not inert:
                endings += 1
                tail_from = after
            at = after
            continue
        at += 1
    if depth != 0:
        raise ValueError("a square bracket was left open")
    if aside:
        raise ValueError("an aside was left open")
    if prose[tail_from:].strip() != "":
        endings += 1
    return endings
