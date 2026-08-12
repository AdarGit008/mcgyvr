"""An account identifier with all but its last digits hidden."""

import re


def mask_account(account: str, keep: int) -> str:
    if not isinstance(account, str):
        raise ValueError("mask_account expects a string")
    if re.fullmatch(r"[0-9 -]+", account) is None:
        raise ValueError("empty account or illegal character")
    if re.search(r"^[ -]|[ -]$|[ -]{2}", account):
        raise ValueError("separators must sit between digit groups")
    if isinstance(keep, bool) or not isinstance(keep, int) or keep < 1:
        raise ValueError("keep must be a whole number of at least 1")
    digits = sum(ch.isdigit() for ch in account)
    if digits < keep:
        raise ValueError("fewer digits than keep")
    hidden = digits - keep
    masked = []
    for ch in account:
        if ch.isdigit() and hidden > 0:
            masked.append("*")
            hidden -= 1
        else:
            masked.append(ch)
    return "".join(masked)
