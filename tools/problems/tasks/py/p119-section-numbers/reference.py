def section_numbers(text: str, unit: int) -> list:
    if not isinstance(unit, int) or isinstance(unit, bool) or unit <= 0:
        raise ValueError("unit must be a positive integer")
    counters = []
    out = []
    previous = -1
    for line in text.split("\n"):
        content = line.lstrip(" ")
        indent = len(line) - len(content)
        if indent % unit != 0:
            raise ValueError("indentation is not a multiple of the unit")
        step = indent // unit
        if step > previous + 1:
            raise ValueError("nesting jumps more than one step")
        while len(counters) <= step:
            counters.append(0)
        counters[step] += 1
        del counters[step + 1 :]
        out.append(".".join(str(c) for c in counters) + " " + content)
        previous = step
    return out
