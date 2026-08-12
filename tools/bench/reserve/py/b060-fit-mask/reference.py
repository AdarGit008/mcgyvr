"""Fit a text to a form input mask: A takes a letter, 9 a digit, else literal."""


def fit_mask(mask, text):
    if not isinstance(mask, str) or not mask:
        raise ValueError("mask must be a non-empty string")
    if not isinstance(text, str):
        raise ValueError("text must be a string")
    if len(text) != len(mask):
        raise ValueError("text length must equal mask length")
    fitted = []
    for ch, c in zip(mask, text):
        if ch == "A" and c.isascii() and c.isalpha():
            fitted.append(c.upper())
        elif ch == "9" and c.isascii() and c.isdigit():
            fitted.append(c)
        elif ch not in "A9" and c == ch:
            fitted.append(c)
        else:
            raise ValueError(f"slot {ch!r} cannot take {c!r}")
    return "".join(fitted)
