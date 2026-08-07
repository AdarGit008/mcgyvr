def _check_slot(key):
    if not key.isdigit() or not key.isascii():
        raise ValueError("slot number must be digits: " + key)
    if len(key) > 1 and key[0] == "0":
        raise ValueError("slot number carries a padding zero")
    if int(key) == 0:
        raise ValueError("slot number is zero")


def _settle(body, slots):
    out = []
    at = 0
    while at < len(body):
        ch = body[at]
        if ch == "{":
            if body[at + 1 : at + 2] == "{":
                out.append("{")
                at += 2
                continue
            close = body.find("}", at + 1)
            if close == -1:
                raise ValueError("brace opened and never closed")
            key = body[at + 1 : close]
            _check_slot(key)
            if key not in slots:
                raise ValueError("splice names a slot not stored yet")
            out.append(slots[key])
            at = close + 1
            continue
        if ch == "}":
            if body[at + 1 : at + 2] == "}":
                out.append("}")
                at += 2
                continue
            raise ValueError("closing brace with nothing open")
        out.append(ch)
        at += 1
    return "".join(out)


def expand_glossary(script: list) -> str:
    if not isinstance(script, list):
        raise ValueError("script must be a list")
    slots = {}
    sent = []
    for line in script:
        if not isinstance(line, str):
            raise ValueError("every line must be a string")
        if line.startswith("!"):
            key = line[1:]
            _check_slot(key)
            if key not in slots:
                raise ValueError("send line names a slot never stored")
            sent.append(slots[key])
            continue
        cut = line.find("=")
        if cut == -1:
            raise ValueError("line is of neither kind")
        key = line[:cut]
        _check_slot(key)
        if key in slots:
            raise ValueError("slot stored a second time")
        slots[key] = _settle(line[cut + 1 :], slots)
    return "".join(sent)
