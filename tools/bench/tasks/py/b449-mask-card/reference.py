def last_four(number: str) -> str:
    if len(number) <= 4:
        return number
    return number[-4:]


def mask_card(number: str) -> str:
    shown = last_four(number)
    return "*" * (len(number) - len(shown)) + shown
