def trim_to(line: str, limit: int) -> str:
    if limit < 4:
        raise ValueError("limit must leave room")
    if len(line) <= limit:
        return line
    return line[: limit - 3] + "..."
