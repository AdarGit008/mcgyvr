def run_transactions(commands: list[str]) -> dict[str, str]:
    base: dict[str, str] = {}
    layers: list[dict[str, str | None]] = []

    for command in commands:
        parts = command.split(" ")
        verb = parts[0]
        if verb == "set":
            if len(parts) != 3:
                raise ValueError(f"set needs a key and a value: {command}")
            if layers:
                layers[-1][parts[1]] = parts[2]
            else:
                base[parts[1]] = parts[2]
        elif verb == "unset":
            if len(parts) != 2:
                raise ValueError(f"unset needs exactly a key: {command}")
            if layers:
                layers[-1][parts[1]] = None
            else:
                base.pop(parts[1], None)
        elif verb == "begin":
            if len(parts) != 1:
                raise ValueError(f"begin takes no parts: {command}")
            layers.append({})
        elif verb == "commit":
            if len(parts) != 1:
                raise ValueError(f"commit takes no parts: {command}")
            if not layers:
                raise ValueError("commit with no open transaction")
            top = layers.pop()
            if layers:
                layers[-1].update(top)
            else:
                for key, value in top.items():
                    if value is None:
                        base.pop(key, None)
                    else:
                        base[key] = value
        elif verb == "rollback":
            if len(parts) != 1:
                raise ValueError(f"rollback takes no parts: {command}")
            if not layers:
                raise ValueError("rollback with no open transaction")
            layers.pop()
        else:
            raise ValueError(f"unknown verb in: {command}")
    if layers:
        raise ValueError("a transaction is still open")
    return base
