import re


def parse_option(segment: str) -> list:
    key, eq, raw = segment.partition("=")
    if not eq or re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", key) is None:
        raise ValueError("malformed option segment: " + segment)
    if len(raw) >= 2 and raw.startswith('"') and raw.endswith('"'):
        raw = raw[1:-1]
    return [key, raw]


def scan_pairs(text: str) -> list:
    if not isinstance(text, str) or not text:
        raise ValueError("scan_pairs expects a non-empty string")
    segments, current, quoted = [], "", False
    for ch in text:
        if ch == '"':
            quoted = not quoted
        if ch == ";" and not quoted:
            segments.append(current)
            current = ""
        else:
            current += ch
    if quoted:
        raise ValueError("unterminated quoted value")
    segments.append(current)
    pairs, seen = [], set()
    for segment in segments:
        key, value = parse_option(segment)
        if key in seen:
            raise ValueError("repeated key: " + key)
        seen.add(key)
        pairs.append([key, value])
    return pairs
