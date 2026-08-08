def nest_outline(text: str) -> list:
    if not isinstance(text, str) or text == "":
        raise ValueError("input must be a non-empty string")
    if "\t" in text:
        raise ValueError("tabs are not allowed")
    lines = text.split("\n")
    if len(lines) > 1 and lines[-1] == "":
        lines.pop()
    roots = []
    stack = []
    previous_depth = -1
    for line in lines:
        body = line.lstrip(" ")
        if body == "":
            raise ValueError("blank lines are not allowed")
        indent = len(line) - len(body)
        if indent % 2 != 0:
            raise ValueError("indentation must be a multiple of two spaces")
        depth = indent // 2
        if depth > previous_depth + 1:
            raise ValueError("a line may nest at most one level deeper")
        node = [body, []]
        del stack[depth:]
        if depth == 0:
            roots.append(node)
        else:
            stack[depth - 1][1].append(node)
        stack.append(node)
        previous_depth = depth
    return roots
