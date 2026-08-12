def turn_text(first: str, second: str) -> bool:
    if len(first) != len(second):
        return False
    if len(first) == 0:
        return True
    return second in first + first
