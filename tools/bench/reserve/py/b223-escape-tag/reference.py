SAFE = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"


def escape_tag(label: str) -> str:
    if not isinstance(label, str) or label == "":
        raise ValueError("a label is a non-empty string")
    out = []
    for ch in label:
        if ord(ch) > 127:
            raise ValueError("a label holds ASCII only")
        out.append(ch if ch in SAFE else f"%{ord(ch):02X}")
    return "".join(out)
