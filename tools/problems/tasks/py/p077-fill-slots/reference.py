def fill_placeholders(text: str, slots: dict) -> str:
    out = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch != "%":
            out.append(ch)
            i += 1
            continue
        if i + 1 < len(text) and text[i + 1] == "%":
            out.append("%")
            i += 2
            continue
        close = text.find("%", i + 1)
        if close == -1:
            raise ValueError("unpaired percent sign")
        name = text[i + 1 : close]
        if name not in slots:
            raise ValueError("unknown slot: " + name)
        out.append(slots[name])
        i = close + 1
    return "".join(out)
