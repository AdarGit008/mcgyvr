"""Billable airtime for a metered call, in whole seconds."""


def billed_airtime(duration, initial, step):
    if isinstance(duration, bool) or not isinstance(duration, int) or duration < 0:
        raise ValueError("duration must be a non-negative integer")
    if isinstance(initial, bool) or not isinstance(initial, int) or initial <= 0:
        raise ValueError("initial block must be a positive integer")
    if isinstance(step, bool) or not isinstance(step, int) or step <= 0:
        raise ValueError("billing step must be a positive integer")
    if duration == 0:
        return 0
    if duration <= initial:
        return initial
    beyond = duration - initial
    steps = -(-beyond // step)
    return initial + steps * step
