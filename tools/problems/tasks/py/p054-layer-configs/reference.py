def _apply_layer(base: dict, layer: dict) -> None:
    for key, incoming in layer.items():
        if incoming is None:
            base.pop(key, None)
        elif isinstance(incoming, dict):
            existing = base.get(key)
            branch = existing if isinstance(existing, dict) else {}
            base[key] = branch
            _apply_layer(branch, incoming)
        else:
            base[key] = incoming


def layer_configs(layers: list[dict]) -> dict:
    if not isinstance(layers, list):
        raise ValueError("layer_configs expects a list of layers")
    result: dict = {}
    for layer in layers:
        if not isinstance(layer, dict):
            raise ValueError("every layer must be a mapping")
        _apply_layer(result, layer)
    return result
