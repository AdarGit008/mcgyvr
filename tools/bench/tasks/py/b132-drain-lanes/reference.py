"""Drain labelled items across planned lanes, round by round."""


def drain_lanes(plan, items):
    if not isinstance(plan, list):
        raise ValueError("the plan must be a list")
    if not plan:
        raise ValueError("the plan must not be empty")
    queues = {}
    for entry in plan:
        if not isinstance(entry, list) or len(entry) != 2:
            raise ValueError("each plan entry must be a lane and a quota")
        lane, quota = entry
        if not isinstance(lane, str) or lane == "":
            raise ValueError("each lane must be a non-empty string")
        if isinstance(quota, bool) or not isinstance(quota, int) or quota < 1:
            raise ValueError("each quota must be a positive integer")
        if lane in queues:
            raise ValueError(f"lane declared twice: {lane}")
        queues[lane] = []
    remaining = 0
    for item in items:
        if not isinstance(item, list) or len(item) != 2:
            raise ValueError("each item must be a label and a lane")
        label, lane = item
        if not isinstance(label, str):
            raise ValueError("each label must be a string")
        if not isinstance(lane, str):
            raise ValueError("each item lane must be a string")
        if lane not in queues:
            raise ValueError(f"item for an undeclared lane: {lane}")
        queues[lane].append(label)
        remaining += 1
    order = []
    rounds = 0
    while remaining > 0:
        rounds += 1
        for lane, quota in plan:
            queue = queues[lane]
            taken = 0
            while taken < quota and queue:
                order.append(queue.pop(0))
                taken += 1
                remaining -= 1
    return {"order": order, "rounds": rounds}
