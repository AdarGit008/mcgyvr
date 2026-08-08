def _positive_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def first_deadline_miss(jobs: list[dict]) -> str:
    seen = set()
    for job in jobs:
        name = job.get("name")
        if not isinstance(name, str) or name == "":
            raise ValueError("name must be a non-empty string")
        if name in seen:
            raise ValueError(f"name repeated: {name}")
        seen.add(name)
        if not _positive_int(job.get("work")):
            raise ValueError("work must be a positive integer")
        if not _positive_int(job.get("due")):
            raise ValueError("due must be a positive integer")
    clock = 0
    for job in sorted(jobs, key=lambda j: j["due"]):
        clock += job["work"]
        if clock > job["due"]:
            return job["name"]
    return ""
