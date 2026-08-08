FOLDS = ("keep", "up", "down")


def stack_address_panel(parts: dict, plan: list) -> list:
    if not isinstance(parts, dict):
        raise ValueError("parts must be a record")
    if not isinstance(plan, list) or len(plan) == 0:
        raise ValueError("plan must be a list holding at least one step")
    lines = []
    for step in plan:
        if not isinstance(step, dict):
            raise ValueError("each step must be a record")
        slots = step.get("slots")
        if not isinstance(slots, list) or len(slots) == 0:
            raise ValueError("slots must be a list holding at least one slot name")
        for slot in slots:
            if not isinstance(slot, str) or slot == "":
                raise ValueError("a slot name must be a non-empty string")
        fold = step.get("fold")
        if fold not in FOLDS:
            raise ValueError("fold must be one of keep, up, down")
        must = step.get("must")
        if not isinstance(must, bool):
            raise ValueError("must must be a boolean")
        pieces = []
        for slot in slots:
            text = parts.get(slot)
            if not isinstance(text, str):
                continue
            trimmed = text.strip()
            if trimmed == "":
                continue
            pieces.append(trimmed)
        if not pieces:
            if must:
                raise ValueError(f"the step wanting {slots[0]} found nothing to write")
            continue
        line = " ".join(pieces)
        if fold == "up":
            lines.append(line.upper())
        elif fold == "down":
            lines.append(line.lower())
        else:
            lines.append(line)
    return lines
