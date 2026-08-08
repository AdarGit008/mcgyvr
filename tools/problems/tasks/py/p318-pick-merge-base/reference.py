def pick_merge_base(parents: dict, left: str, right: str) -> str:
    if not isinstance(parents, dict):
        raise ValueError("the history must be a mapping of revision to parents")
    names = list(parents)
    for name in names:
        listed = parents[name]
        if not isinstance(listed, list):
            raise ValueError(f"revision {name} does not list its parents")
        seen = set()
        for parent in listed:
            if not isinstance(parent, str) or parent not in parents:
                raise ValueError(f"revision {name} names an unknown parent")
            if parent in seen:
                raise ValueError(f"revision {name} names {parent} twice")
            seen.add(parent)

    pending = {name: len(parents[name]) for name in names}
    children = {name: [] for name in names}
    for name in names:
        for parent in parents[name]:
            children[parent].append(name)
    ready = [name for name in names if pending[name] == 0]
    settled = 0
    while ready:
        name = ready.pop()
        settled += 1
        for child in children[name]:
            pending[child] -= 1
            if pending[child] == 0:
                ready.append(child)
    if settled != len(names):
        raise ValueError("a revision descends from itself")

    for name in (left, right):
        if not isinstance(name, str) or name not in parents:
            raise ValueError(f"the history carries no revision {name}")

    def forebears(start):
        reached = {start}
        stack = [start]
        while stack:
            name = stack.pop()
            for parent in parents[name]:
                if parent not in reached:
                    reached.add(parent)
                    stack.append(parent)
        return reached

    shared = sorted(forebears(left) & forebears(right))
    if not shared:
        raise ValueError("the two revisions share no forebear")
    covered = set()
    for name in shared:
        covered |= forebears(name) - {name}
    for name in shared:
        if name not in covered:
            return name
    raise ValueError("the two revisions share no forebear")
