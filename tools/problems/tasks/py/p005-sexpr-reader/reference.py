import re

_INTEGER = re.compile(r"-?[0-9]+")
_SYMBOL = re.compile(r"[A-Za-z0-9+\-*/!?]+")


def read_sexpr(text: str) -> object:
    if not isinstance(text, str):
        raise ValueError("read_sexpr expects a string")
    pos = 0
    length = len(text)

    def skip_ws():
        nonlocal pos
        while pos < length and text[pos] in " \t\r\n":
            pos += 1

    def parse():
        nonlocal pos
        skip_ws()
        if pos >= length:
            raise ValueError("unexpected end of input")
        ch = text[pos]
        if ch == "(":
            pos += 1
            items = []
            while True:
                skip_ws()
                if pos >= length:
                    raise ValueError("unclosed list")
                if text[pos] == ")":
                    pos += 1
                    return items
                items.append(parse())
        if ch == ")":
            raise ValueError("stray closing parenthesis")
        start = pos
        while pos < length and text[pos] not in " \t\r\n()":
            pos += 1
        token = text[start:pos]
        if _INTEGER.fullmatch(token):
            return int(token)
        if token[0].isdigit():
            raise ValueError("atom starting with a digit must be an integer")
        if _SYMBOL.fullmatch(token) is None:
            raise ValueError("atom has a character outside the symbol set")
        return token

    value = parse()
    skip_ws()
    if pos < length:
        raise ValueError("trailing content after the expression")
    return value
