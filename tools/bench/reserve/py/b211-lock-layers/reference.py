"""Fold configuration layers, honouring the locks declared along the way."""


def resolve_layers(layers: list[dict]) -> dict[str, str]:
    settled: dict[str, str] = {}
    frozen: set[str] = set()
    for layer in layers:
        for name, value in layer["set"].items():
            if name not in frozen:
                settled[name] = value
        for name in layer["drop"]:
            if name not in frozen:
                settled.pop(name, None)
        for name in layer["lock"]:
            frozen.add(name)
    return settled
