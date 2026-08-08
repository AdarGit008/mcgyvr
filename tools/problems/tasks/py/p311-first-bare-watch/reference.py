import re


def first_bare_watch(on_duty: list[list[str]], warrants: list[list[str]]) -> int:
    if not isinstance(on_duty, list) or not on_duty:
        raise ValueError("the duty list must be a non-empty list")
    for watch in on_duty:
        if not isinstance(watch, list):
            raise ValueError("every watch entry is a list")
        for held in watch:
            if not isinstance(held, str) or not held:
                raise ValueError("every warrant on watch is a non-empty name")
    if not isinstance(warrants, list) or not warrants:
        raise ValueError("the standing order must be a non-empty list")
    order = []
    demanded = set()
    for row in warrants:
        if not isinstance(row, list) or len(row) != 2:
            raise ValueError("every standing order row is a pair")
        for field in row:
            if not isinstance(field, str) or not field:
                raise ValueError("every standing order field is a non-empty string")
        if re.fullmatch(r"[0-9]+", row[1]) is None:
            raise ValueError("a headcount is written in decimal figures")
        least = int(row[1])
        if least < 1:
            raise ValueError("a standing order musters at least one hand")
        if row[0] in demanded:
            raise ValueError("that warrant is demanded twice over")
        demanded.add(row[0])
        order.append((row[0], least))

    for number, watch in enumerate(on_duty, 1):
        mustered: dict[str, int] = {}
        for held in watch:
            mustered[held] = mustered.get(held, 0) + 1
        for warrant, least in order:
            if mustered.get(warrant, 0) < least:
                return number
    return 0
