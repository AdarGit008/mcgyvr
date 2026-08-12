def repeat_text(phrase: str, times: int, between: str) -> str:
    if times <= 0:
        return ""
    copies = [phrase] * times
    return between.join(copies)
