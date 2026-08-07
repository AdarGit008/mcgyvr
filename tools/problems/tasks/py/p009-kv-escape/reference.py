"""One line of key=value pairs, joined by &."""


def _escape(text):
    return text.replace("%", "%25").replace("&", "%26").replace("=", "%3D")


def encode_pairs(pairs):
    if not isinstance(pairs, list):
        raise ValueError("encode_pairs expects a list of pairs")
    parts = []
    for pair in pairs:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            raise ValueError("each entry is a key-value pair")
        key, value = pair
        if not isinstance(key, str) or not isinstance(value, str):
            raise ValueError("keys and values must be strings")
        if key == "":
            raise ValueError("empty key")
        parts.append(_escape(key) + "=" + _escape(value))
    return "&".join(parts)
