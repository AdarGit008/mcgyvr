import re

_IDENT = r"[A-Za-z_][A-Za-z0-9_]*"
_INDEX = r"\[(?:0|[1-9][0-9]*)\]"
_PATH = re.compile(rf"{_IDENT}(?:{_INDEX})*(?:\.{_IDENT}(?:{_INDEX})*)*")


def split_field_path(path: str) -> list:
    if not isinstance(path, str):
        raise ValueError("split_field_path expects a string")
    if _PATH.fullmatch(path) is None:
        raise ValueError("malformed field path")
    parts = []
    for match in re.finditer(r"([A-Za-z_][A-Za-z0-9_]*)|\[([0-9]+)\]", path):
        if match.group(1) is not None:
            parts.append(match.group(1))
        else:
            parts.append(int(match.group(2)))
    return parts
