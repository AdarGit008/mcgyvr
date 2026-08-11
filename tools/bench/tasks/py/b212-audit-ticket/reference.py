"""Name the first fault a depot ticket carries, or call it ok."""

import re

ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def audit_ticket(ticket: str) -> str:
    if not isinstance(ticket, str):
        raise ValueError("audit_ticket expects a string")
    if re.fullmatch(r"[A-Z]{2}-\d{4}-\d", ticket) is None:
        return "shape"
    prefix, run, check = ticket.split("-")
    total = 0
    for letter in prefix:
        total += ALPHABET.index(letter) + 1
    for spot, digit in enumerate(run, start=1):
        total += int(digit) * spot
    if total % 10 != int(check):
        return "check"
    return "ok"
