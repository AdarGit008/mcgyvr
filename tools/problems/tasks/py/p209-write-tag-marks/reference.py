import re

SHAPE = re.compile(r"[a-z][a-z0-9]*")
NAKED = re.compile(r"[A-Za-z0-9.-]+")


def write_tag_marks(label: str, fields: list) -> str:
    if not isinstance(label, str) or SHAPE.fullmatch(label) is None:
        raise ValueError("the label breaks its shape")
    if not isinstance(fields, list):
        raise ValueError("the fields must be a list")
    arrived = set()
    out = "<" + label
    for entry in fields:
        if not isinstance(entry, list) or len(entry) != 2:
            raise ValueError("every field must be a list of exactly two")
        key, text = entry
        if not isinstance(key, str) or SHAPE.fullmatch(key) is None:
            raise ValueError("a key breaks its shape")
        if not isinstance(text, str):
            raise ValueError("a text must be a string")
        if key in arrived:
            raise ValueError("the key " + key + " arrives twice")
        arrived.add(key)
        out += " " + key
        if text == "":
            continue
        if NAKED.fullmatch(text) is not None:
            out += "=" + text
            continue
        fence = "'" if '"' in text and "'" not in text else '"'
        body = ""
        for ch in text:
            if ch == "\\" or ch == fence:
                body += "\\"
            body += ch
        out += "=" + fence + body + fence
    return out + ">"
