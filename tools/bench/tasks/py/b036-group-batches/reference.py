"""Schedule grouped jobs into weighted batches.

Jobs arrive as [name, group, priority, weight] quadruples; within a group,
jobs must run in arrival order, so only the earliest unscheduled job of
each group is ever eligible. Each round fills one batch: eligible heads
are ranked by urgency and taken first-fit against the batch's weight
capacity.
"""


def group_batches(jobs: list, capacity: int) -> list:
    if not isinstance(jobs, list):
        raise ValueError("jobs must be a list")
    if isinstance(capacity, bool) or not isinstance(capacity, int):
        raise ValueError("capacity must be a positive integer")
    if capacity < 1:
        raise ValueError("capacity must be a positive integer")
    seen = set()
    for job in jobs:
        if not isinstance(job, list) or len(job) != 4:
            raise ValueError("each job is a [name, group, priority, weight] quadruple")
        name, group, priority, weight = job
        if not isinstance(name, str) or name == "":
            raise ValueError("job name must be a non-empty string")
        if not isinstance(group, str) or group == "":
            raise ValueError("job group must be a non-empty string")
        if isinstance(priority, bool) or not isinstance(priority, int):
            raise ValueError("job priority must be an integer")
        if isinstance(weight, bool) or not isinstance(weight, int):
            raise ValueError("job weight must be an integer from 1 to capacity")
        if weight < 1 or weight > capacity:
            raise ValueError("job weight must be an integer from 1 to capacity")
        if name in seen:
            raise ValueError("job names must be unique")
        seen.add(name)
    # Per-group queues in arrival order; each holds global arrival indexes.
    queues = {}
    order = []
    for index, job in enumerate(jobs):
        group = job[1]
        if group not in queues:
            queues[group] = []
            order.append(group)
        queues[group].append(index)
    batches = []
    remaining = len(jobs)
    while remaining > 0:
        # The heads: the earliest unscheduled job of every non-empty group.
        heads = [queues[group][0] for group in order if queues[group]]
        heads.sort(key=lambda index: (-jobs[index][2], index))
        # First-fit in urgency order: a head too heavy for what is left of
        # this batch is passed over; later, lighter heads may still fit.
        batch = []
        load = 0
        for index in heads:
            weight = jobs[index][3]
            if load + weight > capacity:
                continue
            batch.append(jobs[index][0])
            load += weight
            queues[jobs[index][1]].pop(0)
            remaining -= 1
        batches.append(batch)
    return batches
