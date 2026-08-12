def clip_text(text: str, start: int, end: int) -> str:
    if start > end:
        raise ValueError("the first place must not stand above the second")
    low = len(text) if start > len(text) else start
    high = len(text) if end > len(text) else end
    return text[low:high]
