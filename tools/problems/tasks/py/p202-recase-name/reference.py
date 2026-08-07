import re

STYLES = ("snake", "kebab", "shout", "pascal", "camel")


def _is_upper(ch: str) -> bool:
    return "A" <= ch <= "Z"


def _is_lower(ch: str) -> bool:
    return "a" <= ch <= "z"


def _is_digit(ch: str) -> bool:
    return "0" <= ch <= "9"


def _cut_words(label: str) -> list:
    words = []
    for segment in re.split(r"[_-]", label):
        at = 0
        size = len(segment)
        while at < size:
            head = segment[at]
            if _is_digit(head):
                end = at
                while end < size and _is_digit(segment[end]):
                    end += 1
                words.append(segment[at:end])
                at = end
            elif _is_upper(head):
                end = at
                while end < size and _is_upper(segment[end]):
                    end += 1
                if end - at == 1:
                    tail = end
                    while tail < size and _is_lower(segment[tail]):
                        tail += 1
                    words.append(segment[at:tail])
                    at = tail
                else:
                    if end < size and _is_lower(segment[end]):
                        end -= 1
                    words.append(segment[at:end])
                    at = end
            else:
                end = at
                while end < size and _is_lower(segment[end]):
                    end += 1
                words.append(segment[at:end])
                at = end
    return words


def _lead_capital(word: str) -> str:
    if re.fullmatch(r"[0-9]+", word) or re.fullmatch(r"[A-Z]{2,}", word):
        return word
    return word[0].upper() + word[1:].lower()


def recase_name(label: str, style: str) -> str:
    if not isinstance(label, str) or not isinstance(style, str):
        raise ValueError("recase_name expects two strings")
    if style not in STYLES:
        raise ValueError("unknown style: " + style)
    if re.fullmatch(r"[A-Za-z0-9]+(?:[_-][A-Za-z0-9]+)*", label) is None:
        raise ValueError("label is empty, oddly punctuated, or holds a stray character")
    words = _cut_words(label)
    if style == "snake":
        return "_".join(word.lower() for word in words)
    if style == "kebab":
        return "-".join(word.lower() for word in words)
    if style == "shout":
        return "_".join(word.upper() for word in words)
    if style == "pascal":
        return "".join(_lead_capital(word) for word in words)
    return words[0].lower() + "".join(_lead_capital(word) for word in words[1:])
