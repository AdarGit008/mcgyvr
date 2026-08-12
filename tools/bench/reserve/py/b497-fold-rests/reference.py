def is_rest(entry: str) -> bool:
    return len(entry.strip()) == 0


def fold_rests(entries: list[str]) -> list[str]:
    """The run with each unbroken stretch of rests standing as one dash."""
    out = []
    resting = False
    for entry in entries:
        if is_rest(entry):
            if not resting:
                out.append("-")
                resting = True
        else:
            out.append(entry)
            resting = False
    return out
