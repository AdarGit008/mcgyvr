def scan_source(line: str) -> list[list[str]]:
    if not isinstance(line, str):
        raise ValueError("input must be a string")
    two_char = ("==", "!=", "<=", ">=", "&&", "||")
    one_char = "=<>+-*/()"
    tokens = []
    i = 0
    while i < len(line):
        ch = line[i]
        if ch in " \t":
            i += 1
            continue
        if ch.isdigit():
            j = i
            while j < len(line) and line[j].isdigit():
                j += 1
            tokens.append(["num", line[i:j]])
            i = j
            continue
        if ch.isalpha() or ch == "_":
            j = i
            while j < len(line) and (line[j].isalnum() or line[j] == "_"):
                j += 1
            tokens.append(["id", line[i:j]])
            i = j
            continue
        if line[i : i + 2] in two_char:
            tokens.append(["op", line[i : i + 2]])
            i += 2
            continue
        if ch in one_char:
            tokens.append(["op", ch])
            i += 1
            continue
        raise ValueError("unexpected character")
    return tokens
