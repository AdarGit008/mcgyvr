import re

_KEY = re.compile(r"[a-z][a-z0-9]*\Z")
_WORD = re.compile(r"[A-Za-z0-9]+")


def expand_shorthand(text: str, table: dict) -> str:
    if not isinstance(text, str):
        raise ValueError("expand_shorthand expects a string of text")
    if not isinstance(table, dict):
        raise ValueError("the table is not a mapping")

    book = {}
    for key, value in table.items():
        if not isinstance(key, str) or _KEY.match(key) is None:
            raise ValueError("a key is not lowercase letters and digits after a letter")
        if not isinstance(value, str) or value == "":
            raise ValueError("a value is not a non-empty string")
        book[key] = value

    def rewrite(found):
        word = found.group(0)
        lowered = word.lower()
        if lowered not in book:
            return word
        value = book[lowered]
        if word == lowered:
            return value
        if word == word.upper():
            return value.upper()
        if word == lowered[0].upper() + lowered[1:]:
            return value[0].upper() + value[1:]
        return word

    return _WORD.sub(rewrite, text)
