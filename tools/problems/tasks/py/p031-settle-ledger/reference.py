def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def settle_ledger(entries: list[dict]) -> list[list]:
    if not isinstance(entries, list):
        raise ValueError("settle_ledger expects a list of entries")
    seen: set[int] = set()
    for entry in entries:
        if not isinstance(entry, dict) or not {"account", "amount", "seq"} <= set(
            entry
        ):
            raise ValueError("entry is missing a required property")
        account = entry["account"]
        amount = entry["amount"]
        seq = entry["seq"]
        if not isinstance(account, str) or account == "":
            raise ValueError("account must be a non-empty string")
        if not _is_int(amount):
            raise ValueError("amount must be an integer")
        if not _is_int(seq):
            raise ValueError("seq must be an integer")
        if seq in seen:
            raise ValueError(f"duplicate seq {seq}")
        seen.add(seq)
    balances: dict[str, int] = {}
    for entry in sorted(entries, key=lambda e: e["seq"]):
        account = entry["account"]
        nxt = balances.get(account, 0) + entry["amount"]
        if nxt < 0:
            raise ValueError(
                f"balance of {account} falls below zero at seq {entry['seq']}"
            )
        balances[account] = nxt
    return [
        [account, balance]
        for account, balance in sorted(balances.items())
        if balance != 0
    ]
