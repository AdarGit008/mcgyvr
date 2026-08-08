def fold_digraphs(text: str, table: list[list[str]]) -> str:
    for pattern, _output in table:
        if pattern == "":
            raise ValueError("empty pattern")
    result = []
    at = 0
    while at < len(text):
        best_pattern = ""
        best_output = ""
        for pattern, output in table:
            if len(pattern) > len(best_pattern) and text.startswith(pattern, at):
                best_pattern = pattern
                best_output = output
        if best_pattern == "":
            result.append(text[at])
            at += 1
        else:
            result.append(best_output)
            at += len(best_pattern)
    return "".join(result)
