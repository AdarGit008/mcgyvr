def _validate(jobs: list[dict]) -> None:
    seen = set()
    for job in jobs:
        name = job.get("name")
        if not isinstance(name, str) or name == "":
            raise ValueError("name must be a non-empty string")
        if name in seen:
            raise ValueError(f"name repeated: {name}")
        seen.add(name)
        at = job.get("at")
        if not isinstance(at, int) or isinstance(at, bool) or at < 0:
            raise ValueError("at must be a non-negative integer")
        for key in ("work", "due"):
            value = job.get(key)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"{key} must be a positive integer")


def preempt_first_overrun(jobs: list[dict]) -> str:
    _validate(jobs)
    remaining = {job["name"]: job["work"] for job in jobs}
    at = {job["name"]: job["at"] for job in jobs}
    due = {job["name"]: job["due"] for job in jobs}
    finish = {}
    clock = 0
    while len(finish) < len(jobs):
        ready = [n for n in remaining if n not in finish and at[n] <= clock]
        if not ready:
            clock = min(at[n] for n in remaining if n not in finish)
            continue
        ready.sort(key=lambda n: (due[n], n))
        run = ready[0]
        arrivals = [minute for minute in at.values() if minute > clock]
        horizon = min(arrivals) if arrivals else None
        available = remaining[run] if horizon is None else min(remaining[run], horizon - clock)
        remaining[run] -= available
        clock += available
        if remaining[run] == 0:
            finish[run] = clock
    missed = [job for job in jobs if finish[job["name"]] > job["due"]]
    if not missed:
        return ""
    missed.sort(key=lambda job: (job["due"], job["name"]))
    return missed[0]["name"]
