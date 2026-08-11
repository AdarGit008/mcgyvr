def throttle_calls(times: list, limit: int, window: int) -> list:
    if not isinstance(times, list):
        raise ValueError("throttle_calls expects a list of arrival times")
    for knob in (limit, window):
        if isinstance(knob, bool) or not isinstance(knob, int) or knob < 1:
            raise ValueError("limit and window must be positive integers")
    for earlier, later in zip([0] + times, times):
        if isinstance(later, bool) or not isinstance(later, int) or later < earlier:
            raise ValueError("arrivals must be non-decreasing non-negative integers")
    accepted, verdicts = [], []
    for now in times:
        accepted = [s for s in accepted if now - s < window]
        verdicts.append(len(accepted) < limit)
        accepted += [now] * verdicts[-1]
    return verdicts
