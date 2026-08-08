import re

_KEY = re.compile(r"[a-z]+( [a-z]+)*\Z")
_VALUE = re.compile(r"[a-z][a-z0-9]*\Z")
_WORDISH = re.compile(r"[A-Za-z0-9]")


def _wordish(character):
    return character != "" and _WORDISH.match(character) is not None


def tighten_note_phrases(text: str, book: dict) -> str:
    if not isinstance(text, str):
        raise ValueError("tighten_note_phrases expects a string of text")
    if not isinstance(book, dict):
        raise ValueError("the book is not a mapping")

    shelf = {}
    for key, value in book.items():
        if not isinstance(key, str) or _KEY.match(key) is None:
            raise ValueError("a key is not lowercase words parted by single spaces")
        if not isinstance(value, str) or _VALUE.match(value) is None:
            raise ValueError(
                "a value is not a contraction of lowercase letters and digits"
            )
        shelf[key] = value

    phrases = sorted(book, key=lambda phrase: (-len(phrase), phrase))
    out = []
    at = 0
    while at < len(text):
        hit = None
        if not _wordish(text[at - 1] if at > 0 else ""):
            for phrase in phrases:
                run = text[at : at + len(phrase)]
                if len(run) != len(phrase) or run.lower() != phrase:
                    continue
                after = at + len(phrase)
                if after < len(text) and _wordish(text[after]):
                    continue
                hit = run
                break
        if hit is None:
            out.append(text[at])
            at += 1
            continue
        value = shelf[hit.lower()]
        opener = hit[0]
        out.append(value[0].upper() + value[1:] if opener != opener.lower() else value)
        at += len(hit)
    return "".join(out)
