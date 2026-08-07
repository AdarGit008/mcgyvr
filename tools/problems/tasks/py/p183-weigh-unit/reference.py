def weigh_unit(spec: str, masses: dict) -> int:
    if not isinstance(spec, str):
        raise ValueError("spec must be a string")
    if len(spec) == 0:
        raise ValueError("spec is empty")
    if not isinstance(masses, dict):
        raise ValueError("masses must be a table")

    at = 0

    def read_count():
        nonlocal at
        if at >= len(spec) or not spec[at].isdigit():
            return 1
        if spec[at] == "0":
            raise ValueError("count starts with the digit zero")
        digits = ""
        while at < len(spec) and spec[at].isdigit():
            digits += spec[at]
            at += 1
        return int(digits)

    def read_spec():
        nonlocal at
        total = 0
        parts = 0
        while at < len(spec) and spec[at] not in ")]":
            ch = spec[at]
            if ch in "([":
                want = ")" if ch == "(" else "]"
                at += 1
                weight = read_spec()
                if at >= len(spec):
                    raise ValueError("opener never answered")
                if spec[at] != want:
                    raise ValueError("opener answered by the other shape")
                at += 1
            else:
                if not ("A" <= ch <= "Z"):
                    raise ValueError("part does not start with a capital letter")
                at += 1
                name = ch
                while at < len(spec) and "a" <= spec[at] <= "z":
                    if len(name) == 3:
                        raise ValueError("name is too long")
                    name += spec[at]
                    at += 1
                if name not in masses:
                    raise ValueError("the table does not hold " + name)
                weight = masses[name]
            total += weight * read_count()
            parts += 1
        if parts == 0:
            raise ValueError("a wrapping with no parts inside it")
        return total

    grand = read_spec()
    if at != len(spec):
        raise ValueError("closer with nothing open")
    return grand
