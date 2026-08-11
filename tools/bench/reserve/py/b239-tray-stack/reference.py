def tray_push(stack: list, item: str) -> list:
    return list(stack) + [item]


def tray_top(stack: list):
    return None if len(stack) == 0 else stack[-1]
