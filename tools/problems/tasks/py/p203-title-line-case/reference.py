import re

TOKEN = re.compile(r"[A-Za-z0-9]+(?:['-][A-Za-z0-9]+)*")


def _dress_token(token: str) -> str:
    pieces = []
    joints = []
    current = ""
    for ch in token:
        if ch in "'-":
            pieces.append(current)
            joints.append(ch)
            current = ""
        else:
            current += ch
    pieces.append(current)
    dressed = []
    for at, piece in enumerate(pieces):
        if at == len(pieces) - 1 and len(pieces) > 1 and len(piece) == 1:
            dressed.append(piece.lower())
        else:
            dressed.append(piece[0].upper() + piece[1:].lower())
    out = dressed[0]
    for at, joint in enumerate(joints):
        out += joint + dressed[at + 1]
    return out


def title_line(text: str, quiet: list) -> str:
    if not isinstance(text, str) or text == "":
        raise ValueError("the heading must be a non-empty string")
    if not isinstance(quiet, list):
        raise ValueError("the quiet list must be a list")
    for entry in quiet:
        if not isinstance(entry, str) or re.fullmatch(r"[a-z]+", entry) is None:
            raise ValueError("every quiet entry must be a string of small letters")
    tokens = text.split(" ")
    for token in tokens:
        if TOKEN.fullmatch(token) is None:
            raise ValueError("malformed token: " + repr(token))
    last = len(tokens) - 1
    out = []
    for at, token in enumerate(tokens):
        if re.fullmatch(r"[A-Z]{2,}", token) is not None:
            out.append(token)
        elif at not in (0, last) and token.lower() in quiet:
            out.append(token.lower())
        else:
            out.append(_dress_token(token))
    return " ".join(out)
