LETTERS = "abcd"


def _read_tract(text):
    if not isinstance(text, str):
        raise ValueError("a tract must be a string")
    slash = text.find("/")
    if slash == -1:
        raise ValueError("a tract needs a slash")
    address = text[:slash]
    tail = text[slash + 1 :]
    if len(tail) != 1 or tail not in "012345":
        raise ValueError("the pinned count must be a single digit from 0 to 5")
    pinned = int(tail)
    if len(address) != 5:
        raise ValueError("an address is exactly five letters")
    start = 0
    for at, letter in enumerate(address):
        digit = LETTERS.find(letter)
        if digit == -1:
            raise ValueError("an address is five letters from a to d")
        if at >= pinned and digit != 0:
            raise ValueError("a letter past the pinned ones must be a")
        start = start * 4 + digit
    return start, 4 ** (5 - pinned)


def _write_tract(start, span):
    pinned = 5
    width = span
    while width > 1:
        width //= 4
        pinned -= 1
    rest = start
    address = ""
    for at in range(4, -1, -1):
        weight = 4**at
        address += LETTERS[rest // weight]
        rest %= weight
    return f"{address}/{pinned}"


def split_address_tracts(root: str, wants: list) -> dict:
    begin, span = _read_tract(root)
    if not isinstance(wants, list) or not wants:
        raise ValueError("there must be at least one want")
    for want in wants:
        if not isinstance(want, int) or isinstance(want, bool) or want < 1:
            raise ValueError("a want must be a whole number above zero")

    order = []
    for at, want in enumerate(wants):
        room = 1
        while room < want:
            room *= 4
        order.append({"at": at, "span": room})
    order.sort(key=lambda item: (-item["span"], item["at"]))

    taken = []
    granted = [""] * len(wants)
    end = begin + span
    for item in order:
        placed = None
        if item["span"] <= span:
            start = begin
            while start + item["span"] <= end:
                clash = any(
                    start < to and frm < start + item["span"] for frm, to in taken
                )
                if not clash:
                    placed = start
                    break
                start += item["span"]
        if placed is None:
            return {"refused": True, "tracts": [], "spare": span}
        taken.append((placed, placed + item["span"]))
        granted[item["at"]] = _write_tract(placed, item["span"])

    used = sum(to - frm for frm, to in taken)
    return {"refused": False, "tracts": granted, "spare": span - used}
