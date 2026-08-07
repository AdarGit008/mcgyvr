def _whole(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def settle_claim_run(claims: object, plan: object) -> list[list[int]]:
    if not isinstance(claims, list):
        raise ValueError("claims must be a list")
    for claim in claims:
        if not _whole(claim) or claim < 0:
            raise ValueError("every claim must be a whole number of cents, not below zero")
    if not isinstance(plan, dict):
        raise ValueError("plan must be a mapping")
    for key in ("deductible", "coinsurance", "cap"):
        if not _whole(plan.get(key)):
            raise ValueError(f"{key} must be a whole number")
    deductible = plan["deductible"]
    coinsurance = plan["coinsurance"]
    cap = plan["cap"]
    if deductible < 0 or cap < 0:
        raise ValueError("deductible and cap must not fall below zero")
    if coinsurance < 0 or coinsurance > 100:
        raise ValueError("coinsurance must be a whole percent from 0 through 100")
    if cap < deductible:
        raise ValueError("cap must not lie below deductible")

    rows: list[list[int]] = []
    unmet = deductible
    running = 0
    for claim in claims:
        swallowed = min(claim, unmet)
        shared = claim - swallowed
        share = (shared * coinsurance + 50) // 100
        owed = swallowed + share
        member = min(owed, cap - running)
        unmet -= swallowed
        running += member
        rows.append([member, claim - member, unmet, running])
    return rows
