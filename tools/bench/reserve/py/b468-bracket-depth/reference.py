def bracket_depth(text: str) -> int:
    open_count = 0
    deepest = 0
    for ch in text:
        if ch == "(":
            open_count += 1
            if open_count > deepest:
                deepest = open_count
        elif ch == ")":
            if open_count == 0:
                raise ValueError("a bracket closes before it opens")
            open_count -= 1
    if open_count != 0:
        raise ValueError("a bracket is left open")
    return deepest
