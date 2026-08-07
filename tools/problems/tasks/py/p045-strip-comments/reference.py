def strip_comments(source: str) -> str:
    if not isinstance(source, str):
        raise ValueError("input must be a string")
    out = []
    i = 0
    while i < len(source):
        ch = source[i]
        if ch == '"':
            j = i + 1
            closed = False
            while j < len(source):
                if source[j] == "\\":
                    j += 2
                    continue
                if source[j] == '"':
                    closed = True
                    j += 1
                    break
                j += 1
            if not closed:
                raise ValueError("unterminated string literal")
            out.append(source[i:j])
            i = j
            continue
        if ch == "/" and source[i : i + 2] == "//":
            while i < len(source) and source[i] != "\n":
                i += 1
            continue
        if ch == "/" and source[i : i + 2] == "/*":
            end = source.find("*/", i + 2)
            if end == -1:
                raise ValueError("unterminated block comment")
            i = end + 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)
