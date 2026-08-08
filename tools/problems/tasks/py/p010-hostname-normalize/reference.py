import re

_LABEL = re.compile(r"[a-z0-9-]+")


def normalize_hostname(hostname: str) -> str:
    if not isinstance(hostname, str):
        raise ValueError("normalize_hostname expects a string")
    name = hostname.lower()
    if name.endswith("."):
        name = name[:-1]
    if len(name) == 0 or len(name) > 253:
        raise ValueError("hostname length is out of range")
    for label in name.split("."):
        if not 1 <= len(label) <= 63:
            raise ValueError("label length is out of range")
        if _LABEL.fullmatch(label) is None:
            raise ValueError("label has an invalid character")
        if label.startswith("-") or label.endswith("-"):
            raise ValueError("label may not start or end with a hyphen")
    return name
