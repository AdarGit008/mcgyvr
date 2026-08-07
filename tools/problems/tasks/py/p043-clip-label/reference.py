def clip_label(label: str, budget: int) -> str:
    if not isinstance(label, str):
        raise ValueError("label must be a string")
    if not isinstance(budget, int) or isinstance(budget, bool) or budget < 4:
        raise ValueError("budget must be an integer of at least 4")
    if len(label) <= budget:
        return label
    kept = label[: budget - 3].rstrip(" ")
    return kept + "..."
