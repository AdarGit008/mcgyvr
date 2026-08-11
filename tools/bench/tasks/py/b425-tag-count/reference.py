def tag_count(line: str) -> int:
    count = 0
    open_now = False
    for ch in line:
        if ch == "<":
            open_now = True
        elif ch == ">":
            if not open_now:
                raise ValueError("a closing bracket with nothing open")
            open_now = False
            count += 1
    return count
