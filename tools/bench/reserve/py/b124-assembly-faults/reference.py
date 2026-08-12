"""A deterministic assembly run: steps consume bins, shortages become faults."""


def run_assembly(bins, steps):
    for part, count in bins.items():
        if not isinstance(part, str) or part == "":
            raise ValueError("bin name must be a non-empty string")
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError("stock must be a non-negative integer")

    def check_step(step):
        if not isinstance(step, list) or len(step) != 3:
            raise ValueError("a step must be a [name, needs, critical] triple")
        name, needs, critical = step
        if not isinstance(name, str) or name == "":
            raise ValueError("step name must be a non-empty string")
        if not isinstance(critical, bool):
            raise ValueError("critical flag must be a boolean")
        for part, needed in needs.items():
            if part not in bins:
                raise ValueError("unknown part: " + str(part))
            if isinstance(needed, bool) or not isinstance(needed, int) or needed < 1:
                raise ValueError("needed count must be a positive integer")

    for step in steps:
        check_step(step)

    stock = dict(bins)
    built = []
    faults = []
    halted = None
    for name, needs, critical in steps:
        short = sorted(part for part in needs if stock[part] < needs[part])
        if not short:
            for part, needed in needs.items():
                stock[part] -= needed
            built.append(name)
            continue
        faults.append([name, short[0]])
        if critical:
            halted = name
            break

    leftover = []
    for part in sorted(stock):
        leftover.append([part, stock[part]])
    return {"built": built, "faults": faults, "halted": halted, "leftover": leftover}
