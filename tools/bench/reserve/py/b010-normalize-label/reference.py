"""Normalize a user-typed label into its canonical hyphenated form."""

RESERVED = ("new", "all", "none")
SEPARATORS = " _-"


def normalize_label(raw: str) -> str:
    if not isinstance(raw, str):
        raise ValueError("label must be a string")
    trimmed = raw.strip()
    for ch in trimmed:
        if not (ch.isascii() and (ch.isalnum() or ch in SEPARATORS)):
            raise ValueError("label contains a forbidden character")
    label = ""
    pending = False
    for ch in trimmed.lower():
        if ch in SEPARATORS:
            pending = label != ""
            continue
        if pending:
            label += "-"
            pending = False
        label += ch
    if label == "":
        raise ValueError("label is empty once normalized")
    if len(label) > 32:
        raise ValueError("label is longer than 32 characters")
    if label in RESERVED:
        raise ValueError("label is a reserved name")
    return label
