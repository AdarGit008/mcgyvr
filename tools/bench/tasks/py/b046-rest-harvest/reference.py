"""The most kilos a picker can take when a worked day forces a rest day."""


def best_harvest(yields):
    if not isinstance(yields, list):
        raise ValueError("best_harvest expects a list of daily yields")
    # Best totals so far, split by whether the previous day was worked.
    rested = 0
    picked = 0
    for kilos in yields:
        if isinstance(kilos, bool) or not isinstance(kilos, int) or kilos < 0:
            raise ValueError("every daily yield must be a non-negative integer")
        # Working today is only lawful on top of a rested yesterday.
        work_today = rested + kilos
        rested = max(rested, picked)
        picked = work_today
    return max(rested, picked)
