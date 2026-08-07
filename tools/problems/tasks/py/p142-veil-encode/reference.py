import string


def veil_encode(keyword: str, message: str) -> str:
    if not isinstance(keyword, str) or not keyword:
        raise ValueError("keyword must be a non-empty string")
    if any(ch not in string.ascii_lowercase for ch in keyword):
        raise ValueError("keyword must be lowercase a-z only")
    if not isinstance(message, str):
        raise ValueError("message must be a string")
    if any(ch != " " and ch not in string.ascii_lowercase for ch in message):
        raise ValueError("message must be lowercase a-z and spaces only")
    veil = []
    for ch in keyword:
        if ch not in veil:
            veil.append(ch)
    for ch in reversed(string.ascii_lowercase):
        if ch not in veil:
            veil.append(ch)
    return "".join(
        ch if ch == " " else veil[ord(ch) - ord("a")] for ch in message
    )
