def tally_reply_removes(links: list[list[str]]) -> list[int]:
    if not isinstance(links, list) or not links:
        raise ValueError("the batch must hold at least one link")
    known: set[str] = set()
    for link in links:
        if not isinstance(link, list) or len(link) != 2:
            raise ValueError("a link is exactly two values")
        for field in link:
            if not isinstance(field, str):
                raise ValueError("a link field must be a string")
        if not link[0]:
            raise ValueError("a note needs an id")
        if link[0] in known:
            raise ValueError("an id is used twice")
        known.add(link[0])

    openers: list[str] = []
    answers_to: dict[str, list[str]] = {}
    for identifier, answers in links:
        if not answers:
            openers.append(identifier)
            continue
        if answers not in known:
            raise ValueError("an answers field names no note in the batch")
        answers_to.setdefault(answers, []).append(identifier)

    counts: list[int] = []
    standing = openers
    reached = 0
    while standing:
        counts.append(len(standing))
        reached += len(standing)
        following: list[str] = []
        for identifier in standing:
            following.extend(answers_to.get(identifier, []))
        standing = following
    if reached != len(links):
        raise ValueError("the answering runs in a circle")
    return counts
