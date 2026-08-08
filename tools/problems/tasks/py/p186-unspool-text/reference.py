def unspool_text(spool: str) -> str:
    if not isinstance(spool, str):
        raise ValueError("spool must be a string")
    out = []
    at = 0
    while at < len(spool):
        ch = spool[at]
        if ch != "<":
            out.append(ch)
            at += 1
            continue
        if spool[at + 1 : at + 2] == "<":
            out.append("<")
            at += 2
            continue
        close = spool.find(">", at + 1)
        if close == -1:
            raise ValueError("pointer whose greater-than sign never arrives")
        body = spool[at + 1 : close]
        comma = body.find(",")
        if comma == -1:
            raise ValueError("pointer with no comma in it")
        fields = [body[:comma], body[comma + 1 :]]
        for field in fields:
            if not field.isdigit() or not field.isascii():
                raise ValueError("pointer field is not digits")
            if len(field) > 1 and field[0] == "0":
                raise ValueError("pointer field carries a padding zero")
            if int(field) == 0:
                raise ValueError("pointer field is zero")
        reach = int(fields[0])
        haul = int(fields[1])
        if reach > len(out):
            raise ValueError("reach is larger than what has been produced")
        for _ in range(haul):
            out.append(out[len(out) - reach])
        at = close + 1
    return "".join(out)
