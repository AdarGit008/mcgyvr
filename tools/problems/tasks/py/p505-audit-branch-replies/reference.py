def audit_branch_replies(sheet: dict) -> dict:
    """Which entries on a branching sheet were owed, spurious or missing."""
    if not isinstance(sheet, dict):
        raise ValueError("the sheet must be a mapping")
    items = sheet.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("the items must be a non-empty list")
    tags = []
    guards = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("an item must be a mapping")
        tag = item.get("tag")
        if not isinstance(tag, str) or not tag:
            raise ValueError("an item needs a non-empty tag")
        if tag in tags:
            raise ValueError("two items carry the same tag")
        when = item.get("when")
        if when is None:
            guards.append(None)
        else:
            if not isinstance(when, dict):
                raise ValueError("a when must be a mapping")
            on = when.get("tag")
            is_ = when.get("is")
            if not isinstance(on, str) or on not in tags:
                raise ValueError("a when must lean on an item standing earlier")
            if not isinstance(is_, str) or not is_:
                raise ValueError("a when needs a non-empty is")
            guards.append((on, is_))
        tags.append(tag)
    given = sheet.get("given")
    if not isinstance(given, dict):
        raise ValueError("the given answers must be a mapping")
    for tag, answer in given.items():
        if tag not in tags:
            raise ValueError("an answer names no item of the sheet")
        if not isinstance(answer, str) or not answer:
            raise ValueError("an answer must be a non-empty string")

    owed = {}
    due = []
    extra = []
    gap = []
    for index, tag in enumerate(tags):
        guard = guards[index]
        if guard is None:
            settled = True
        else:
            settled = owed[guard[0]] and given.get(guard[0]) == guard[1]
        owed[tag] = settled
        answered = tag in given
        if settled:
            due.append(tag)
            if not answered:
                gap.append(tag)
        elif answered:
            extra.append(tag)
    return {"due": due, "extra": extra, "gap": gap}
