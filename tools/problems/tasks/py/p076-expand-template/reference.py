def expand_template(template: str, context: dict, missing: str) -> str:
    if missing not in ("error", "keep", "blank"):
        raise ValueError("unknown policy: " + missing)
    out = []
    i = 0
    while i < len(template):
        ch = template[i]
        if ch != "$":
            out.append(ch)
            i += 1
            continue
        nxt = template[i + 1] if i + 1 < len(template) else ""
        if nxt == "$":
            out.append("$")
            i += 2
            continue
        if nxt != "{":
            raise ValueError("stray dollar sign")
        close = template.find("}", i + 2)
        if close == -1:
            raise ValueError("unclosed placeholder")
        raw = template[i + 2 : close]
        segments = raw.split(".")
        if any(segment == "" for segment in segments):
            raise ValueError("bad path: " + raw)
        value = context
        found = True
        for segment in segments:
            if isinstance(value, dict) and segment in value:
                value = value[segment]
            else:
                found = False
                break
        if not found:
            if missing == "error":
                raise ValueError("missing path: " + raw)
            if missing == "keep":
                out.append(template[i : close + 1])
        elif isinstance(value, str):
            out.append(value)
        elif isinstance(value, int) and not isinstance(value, bool):
            out.append(str(value))
        else:
            raise ValueError("value at " + raw + " is not printable")
        i = close + 1
    return "".join(out)
