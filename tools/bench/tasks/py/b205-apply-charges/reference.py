def _why_refused(cap, left: int, amount: int) -> str:
    if cap is None:
        return "unknown"
    if amount > cap[1]:
        return "single"
    return "cap" if amount > left else ""


def apply_charges(caps: dict, charges: list) -> dict:
    left = {name: cap[0] for name, cap in caps.items()}
    refused = []
    for charge_id, bucket, amount in charges:
        if isinstance(amount, bool) or not isinstance(amount, int) or amount < 1:
            raise ValueError("a charge amount must be a positive whole number")
        reason = _why_refused(caps.get(bucket), left.get(bucket, 0), amount)
        if reason == "":
            left[bucket] -= amount
        else:
            refused.append([charge_id, reason])
    return {"left": left, "refused": refused}
