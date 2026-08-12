def crate_height(kind: str) -> int:
    if kind == "tall":
        return 5
    if kind == "short":
        return 2
    return 3


def crate_stack(kinds: list[str], ceiling: int) -> list[str]:
    """The kinds that fit below a ceiling, in the order given."""
    kept = []
    piled = 0
    for kind in kinds:
        raised = piled + crate_height(kind)
        if raised > ceiling:
            return kept
        piled = raised
        kept.append(kind)
    return kept
