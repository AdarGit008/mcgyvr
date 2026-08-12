def line_number(block: str) -> str:
    if block == "":
        return ""
    out = []
    for i, line in enumerate(block.split("\n")):
        out.append(str(i + 1) + ": " + line)
    return "\n".join(out)
