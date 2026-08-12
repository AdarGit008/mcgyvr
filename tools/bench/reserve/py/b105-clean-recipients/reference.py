"""Tidy a mailing list into canonical recipient addresses."""

import re


def clean_recipients(raw):
    if not isinstance(raw, list):
        raise ValueError("recipients must arrive as a list")
    cleaned = []
    seen = set()
    for entry in raw:
        if not isinstance(entry, str):
            raise ValueError("each recipient must be a string")
        address = entry.strip()
        opens = address.count("<")
        closes = address.count(">")
        if opens or closes:
            good = opens == 1 and closes == 1
            open_at = address.find("<")
            close_at = address.find(">")
            if good and close_at != len(address) - 1:
                good = False
            if good and close_at <= open_at + 1:
                good = False
            if not good:
                raise ValueError("a display entry is text <address>")
            address = address[open_at + 1 : close_at].strip()
        if re.search(r"\s", address):
            raise ValueError("an address holds no inner whitespace")
        pieces = address.split("@")
        if len(pieces) != 2:
            raise ValueError("an address holds exactly one @")
        local, domain = pieces[0], pieces[1].lower()
        if not local:
            raise ValueError("the local part must not be empty")
        if not domain or "." not in domain:
            raise ValueError("the domain needs inner dots")
        if domain.startswith(".") or domain.endswith("."):
            raise ValueError("the domain needs inner dots")
        canonical = local + "@" + domain
        key = canonical.lower()
        if key not in seen:
            seen.add(key)
            cleaned.append(canonical)
    return cleaned
