def line_trim(block: str) -> str:
    trimmed = []
    for line in block.split("\n"):
        trimmed.append(line.rstrip(" "))
    return "\n".join(trimmed)
