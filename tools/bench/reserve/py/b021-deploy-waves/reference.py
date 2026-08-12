"""Deployment order of services as waves of a dependency graph."""


def _catalog_of(services):
    requires_of = {}
    for name, requires in services:
        if not isinstance(name, str) or not name:
            raise ValueError("service name must be a non-empty string")
        if name in requires_of:
            raise ValueError(f"duplicate service: {name}")
        requires_of[name] = requires
    return requires_of


def _check_edges(requires_of):
    for name, requires in requires_of.items():
        seen = set()
        for dep in requires:
            if not isinstance(dep, str):
                raise ValueError(f"non-string dependency on service: {name}")
            if dep == name:
                raise ValueError(f"service depends on itself: {name}")
            if dep not in requires_of:
                raise ValueError(f"unknown dependency: {dep}")
            if dep in seen:
                raise ValueError(f"dependency listed twice: {dep}")
            seen.add(dep)


def deploy_waves(services: list) -> list:
    requires_of = _catalog_of(services)
    _check_edges(requires_of)
    placed = set()
    waves = []
    while len(placed) < len(requires_of):
        ready = [
            name
            for name, requires in requires_of.items()
            if name not in placed and all(dep in placed for dep in requires)
        ]
        if not ready:
            raise ValueError("dependency cycle detected")
        ready.sort()
        waves.append(ready)
        placed.update(ready)
    return waves
