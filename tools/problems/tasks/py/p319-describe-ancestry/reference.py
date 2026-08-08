def describe_ancestry(history: dict, one: str, other: str) -> str:
    if not isinstance(history, dict):
        raise ValueError("the history must be a mapping of checkpoint to predecessors")
    for name in history:
        listed = history[name]
        if not isinstance(listed, list):
            raise ValueError(f"checkpoint {name} does not list its predecessors")
        for earlier in listed:
            if not isinstance(earlier, str):
                raise ValueError(
                    f"checkpoint {name} lists a predecessor that is not a name"
                )
            if earlier not in history:
                raise ValueError(f"checkpoint {name} lists the unknown {earlier}")
    for name in (one, other):
        if not isinstance(name, str) or name not in history:
            raise ValueError(f"the history carries no checkpoint {name}")

    if one == other:
        return "same"

    def steps_back(start, goal):
        ring = [start]
        walked = {start}
        steps = 0
        while ring:
            steps += 1
            onward = []
            for name in ring:
                for earlier in history[name]:
                    if earlier == goal:
                        return steps
                    if earlier not in walked:
                        walked.add(earlier)
                        onward.append(earlier)
            ring = onward
        return -1

    back = steps_back(other, one)
    if back > 0:
        return f"behind:{back}"
    forward = steps_back(one, other)
    if forward > 0:
        return f"ahead:{forward}"
    return "apart"
