def read_switches(kinds: dict, tokens: list[str]) -> dict:
    found = {}
    extra = []
    i = 0
    while i < len(tokens):
        token = tokens[i]
        i += 1
        if not token.startswith("--"):
            extra.append(token)
            continue
        body = token[2:]
        name, sep, text = body.partition("=")
        if name not in kinds:
            raise ValueError(f"unknown option {name}")
        if kinds[name] == "switch":
            if sep:
                raise ValueError(f"switch {name} takes no text")
            found[name] = True
        elif sep:
            found[name] = text
        else:
            if i >= len(tokens):
                raise ValueError(f"value option {name} has nothing following")
            found[name] = tokens[i]
            i += 1
    return {"found": found, "extra": extra}
