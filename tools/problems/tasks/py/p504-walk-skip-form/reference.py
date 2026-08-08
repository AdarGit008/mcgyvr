def walk_skip_form(steps: list, replies: dict) -> dict:
    if not isinstance(steps, list) or not steps:
        raise ValueError("the steps must be a non-empty list")
    codes = []
    place = {}
    for step in steps:
        if not isinstance(step, dict):
            raise ValueError("a step must be a mapping")
        code = step.get("code")
        if not isinstance(code, str) or not code:
            raise ValueError("a step needs a non-empty code")
        if code in place:
            raise ValueError("two steps carry the same code")
        place[code] = len(codes)
        codes.append(code)

    options = []
    jumps = []
    for index, step in enumerate(steps):
        choices = step.get("options")
        if not isinstance(choices, list) or not choices:
            raise ValueError("a step needs a non-empty list of options")
        kept = []
        for choice in choices:
            if not isinstance(choice, str) or not choice:
                raise ValueError("an option must be a non-empty string")
            if choice in kept:
                raise ValueError("a step repeats an option")
            kept.append(choice)
        options.append(kept)
        rules = step.get("jumps")
        if not isinstance(rules, list):
            raise ValueError("the jumps of a step must be a list")
        table = {}
        for rule in rules:
            if not isinstance(rule, dict):
                raise ValueError("a jump must be a mapping")
            on = rule.get("on")
            to = rule.get("to")
            if not isinstance(on, str) or on not in kept:
                raise ValueError("a jump must fire on one of its own step's options")
            if on in table:
                raise ValueError("two jumps of one step fire on the same option")
            if not isinstance(to, str):
                raise ValueError("a jump needs a target")
            if to != "close" and not (to in place and place[to] > index):
                raise ValueError("a jump must go to close or to a later step")
            table[on] = to
        jumps.append(table)

    if not isinstance(replies, dict):
        raise ValueError("the replies must be a mapping")
    for code, value in replies.items():
        if code not in place:
            raise ValueError("a reply names no step of the form")
        if not isinstance(value, str):
            raise ValueError("a reply must be a string")

    asked = []
    blank = []
    wrong = []
    reached = set()
    ending = "spent"
    at = 0
    while at < len(steps):
        code = codes[at]
        asked.append(code)
        reached.add(code)
        if code not in replies:
            blank.append(code)
            at += 1
            continue
        answer = replies[code]
        if answer not in options[at]:
            wrong.append(code)
            at += 1
            continue
        target = jumps[at].get(answer)
        if target is None:
            at += 1
        elif target == "close":
            ending = "close"
            break
        else:
            at = place[target]

    stray = [code for code in codes if code not in reached and code in replies]
    return {"asked": asked, "blank": blank, "wrong": wrong, "stray": stray, "ending": ending}
