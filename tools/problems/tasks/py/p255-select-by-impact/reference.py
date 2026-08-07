from collections import deque


def select_by_impact(imports: dict, suites: dict, edited: list[str]) -> list[str]:
    if not isinstance(imports, dict):
        raise ValueError("the module graph must be a table")
    if not isinstance(suites, dict):
        raise ValueError("the suite table must be a table")
    if not isinstance(edited, list):
        raise ValueError("the edited modules must be a list")

    known = set(imports)
    importers = {module: [] for module in known}
    for module, targets in imports.items():
        if not isinstance(targets, list):
            raise ValueError(f"{module} must list its imports")
        seen = set()
        for target in targets:
            if not isinstance(target, str) or target not in known:
                raise ValueError(f"{module} imports the undeclared {target!r}")
            if target == module:
                raise ValueError(f"{module} imports itself")
            if target in seen:
                raise ValueError(f"{module} imports {target} twice")
            seen.add(target)
            importers[target].append(module)

    disturbed = set()
    queue = deque()
    for name in edited:
        if not isinstance(name, str) or name not in known:
            raise ValueError(f"edited module {name!r} is not declared")
        if name not in disturbed:
            disturbed.add(name)
            queue.append(name)
    while queue:
        module = queue.popleft()
        for importer in importers.get(module, ()):
            if importer not in disturbed:
                disturbed.add(importer)
                queue.append(importer)

    running = []
    total = 0
    for suite, modules in suites.items():
        if suite == "":
            raise ValueError("a suite name cannot be empty")
        if not isinstance(modules, list):
            raise ValueError(f"{suite} must drive a list of modules")
        for module in modules:
            if not isinstance(module, str) or module not in known:
                raise ValueError(f"{suite} drives the undeclared {module!r}")
        total += 1
        if any(module in disturbed for module in modules):
            running.append(suite)
    if len(running) * 2 > total:
        return ["ALL"]
    return sorted(running)
