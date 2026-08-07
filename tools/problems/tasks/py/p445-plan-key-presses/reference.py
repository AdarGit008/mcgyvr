def plan_key_presses(text: str, layout: list) -> str:
    if not isinstance(text, str):
        raise ValueError("the text must be a string")
    if text == "":
        raise ValueError("the text is empty")
    if not isinstance(layout, list) or len(layout) != 10:
        raise ValueError("the layout is exactly ten keys")

    place = {}
    for key, carried in enumerate(layout):
        if not isinstance(carried, str):
            raise ValueError(f"key {key} does not carry a string")
        for at, mark in enumerate(carried):
            if mark in place:
                raise ValueError(f"the layout lists {mark} more than once")
            place[mark] = (key, at + 1)

    parts = []
    previous = -1
    for mark in text:
        if mark not in place:
            raise ValueError(f"{mark} sits on no key")
        key, presses = place[mark]
        if key == previous:
            parts.append(".")
        parts.append(str(key) * presses)
        previous = key
    return "".join(parts)
