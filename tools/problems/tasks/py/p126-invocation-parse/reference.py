def parse_invocation(catalogue: list[dict], tokens: list[str]) -> dict:
    by_name = {}
    by_alias = {}
    options = {}
    for entry in catalogue:
        by_name[entry["name"]] = entry
        if "alias" in entry:
            by_alias[entry["alias"]] = entry
        if entry["kind"] == "toggle":
            options[entry["name"]] = False
        elif entry["kind"] == "single":
            options[entry["name"]] = None
        else:
            options[entry["name"]] = []
    operands = []
    seen_single = set()
    options_done = False
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if options_done:
            operands.append(token)
            i += 1
            continue
        if token == "--":
            options_done = True
            i += 1
            continue
        entry = None
        inline = None
        has_inline = False
        if token.startswith("--"):
            body = token[2:]
            name, sep, rest = body.partition("=")
            if sep:
                inline = rest
                has_inline = True
            entry = by_name.get(name)
            if entry is None:
                raise ValueError(f"unknown option {name}")
        elif token.startswith("-") and len(token) == 2:
            entry = by_alias.get(token[1])
            if entry is None:
                raise ValueError(f"unknown alias {token}")
        else:
            operands.append(token)
            i += 1
            continue
        i += 1
        if entry["kind"] == "toggle":
            if has_inline:
                raise ValueError(f"toggle {entry['name']} takes no value")
            options[entry["name"]] = True
            continue
        if has_inline:
            value = inline
        else:
            if i >= len(tokens):
                raise ValueError(f"option {entry['name']} is missing its value")
            value = tokens[i]
            i += 1
        if entry["kind"] == "single":
            if entry["name"] in seen_single:
                raise ValueError(f"single option {entry['name']} mentioned twice")
            seen_single.add(entry["name"])
            options[entry["name"]] = value
        else:
            options[entry["name"]].append(value)
    return {"options": options, "operands": operands}
