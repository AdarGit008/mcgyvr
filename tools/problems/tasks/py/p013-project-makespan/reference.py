def project_makespan(durations: dict[str, int], deps: list[list[str]]) -> int:
    for name, minutes in durations.items():
        if isinstance(minutes, bool) or not isinstance(minutes, int) or minutes <= 0:
            raise ValueError(f"duration of {name} must be a positive whole number")
    prereqs: dict[str, list[str]] = {}
    for before, after in deps:
        if before not in durations or after not in durations:
            raise ValueError("dependency names a task absent from the mapping")
        if before == after:
            raise ValueError("a task cannot depend on itself")
        prereqs.setdefault(after, []).append(before)

    finish: dict[str, int] = {}
    on_path: set[str] = set()

    def finish_time(name: str) -> int:
        if name in finish:
            return finish[name]
        if name in on_path:
            raise ValueError("dependencies form a cycle")
        on_path.add(name)
        start = 0
        for need in prereqs.get(name, ()):
            start = max(start, finish_time(need))
        on_path.discard(name)
        finish[name] = start + durations[name]
        return finish[name]

    return max(finish_time(name) for name in durations)
