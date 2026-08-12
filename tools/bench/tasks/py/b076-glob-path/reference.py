def glob_path(pattern: str, path: str) -> bool:
    if not isinstance(pattern, str) or not isinstance(path, str):
        raise ValueError("glob_path expects two strings")
    if not pattern or not path:
        raise ValueError("empty pattern or path")

    def step(p: int, s: int) -> bool:
        if p == len(pattern):
            return s == len(path)
        ch = pattern[p]
        if ch == "*":
            if step(p + 1, s):
                return True
            return s < len(path) and path[s] != "/" and step(p, s + 1)
        if s == len(path):
            return False
        if ch == "?":
            return path[s] != "/" and step(p + 1, s + 1)
        return path[s] == ch and step(p + 1, s + 1)

    return step(0, 0)
