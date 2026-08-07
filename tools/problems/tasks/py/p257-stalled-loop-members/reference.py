def stalled_loop_members(waits: dict) -> list:
    if not isinstance(waits, dict):
        raise ValueError("stalled_loop_members expects a stall table")
    for job, target in waits.items():
        if not isinstance(job, str) or job == "":
            raise ValueError("a stalled job cannot have an empty name")
        if not isinstance(target, str) or target == "":
            raise ValueError(f"{job} waits on something that is not a job name")
        if job == target:
            raise ValueError(f"{job} waits on itself")

    size = len(waits)

    def closes(job):
        current = job
        for _ in range(size + 1):
            if current not in waits:
                return False
            current = waits[current]
            if current == job:
                return True
        return False

    looped = [job for job in waits if closes(job)]
    if not looped:
        return []
    start = min(looped)
    members = [start]
    current = waits[start]
    while current != start:
        members.append(current)
        current = waits[current]
    return sorted(members)
