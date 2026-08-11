def config_value(layers, name):
    if not isinstance(name, str) or not name:
        raise ValueError("name must be a non-empty string")
    found = None
    for layer in layers:
        if not isinstance(layer, str):
            raise ValueError("each layer must be a string")
        for raw in layer.split("\n"):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("!"):
                if line[1:].strip() == name:
                    found = None
                continue
            eq = line.find("=")
            if eq <= 0:
                raise ValueError(f"malformed line: {raw}")
            if line[:eq].strip() == name:
                found = line[eq + 1:].strip()
    return found
