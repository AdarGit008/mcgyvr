NAMES = ("won", "lost", "held")


def _whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def plan_retry_window(policy, outcomes):
    if not isinstance(policy, dict):
        raise ValueError("the policy must be a record")
    for field in ("base", "factor", "ceiling", "tries", "deadline"):
        if field not in policy:
            raise ValueError("the policy is missing " + field)
    base = policy["base"]
    factor = policy["factor"]
    ceiling = policy["ceiling"]
    tries = policy["tries"]
    deadline = policy["deadline"]
    for value in (base, factor, tries, deadline):
        if not _whole(value) or value < 1:
            raise ValueError("base, factor, tries and deadline must be one or more")
    if not _whole(ceiling) or ceiling < base:
        raise ValueError("ceiling must be a whole number of at least base")
    if not isinstance(outcomes, list):
        raise ValueError("the outcomes must be a list")
    for outcome in outcomes:
        if not isinstance(outcome, str) or outcome not in NAMES:
            raise ValueError("an outcome must be won, lost or held")
    times = [0]
    made = 1
    streak = 0
    while True:
        if made > len(outcomes):
            raise ValueError("the outcome list ends while the plan is still going")
        outcome = outcomes[made - 1]
        if outcome == "won":
            return {"times": times, "verdict": "succeeded"}
        if made == tries:
            return {"times": times, "verdict": "exhausted"}
        if outcome == "lost":
            streak += 1
            gap = base
            for _grown in range(1, streak):
                gap = gap * factor
                if gap > ceiling:
                    gap = ceiling
            if gap > ceiling:
                gap = ceiling
        else:
            streak = 0
            gap = ceiling
        following = times[-1] + gap
        if following >= deadline:
            return {"times": times, "verdict": "expired"}
        times.append(following)
        made += 1
