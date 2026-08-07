def transcribe_runes(source: str, table: list[list[str]]) -> str:
    for pattern, _output in table:
        if pattern == "":
            raise ValueError("empty pattern in rule table")
    result = []
    at = 0
    while at < len(source):
        for pattern, output in table:
            if source.startswith(pattern, at):
                result.append(output)
                at += len(pattern)
                break
        else:
            result.append(source[at])
            at += 1
    return "".join(result)
