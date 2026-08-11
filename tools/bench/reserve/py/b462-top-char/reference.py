def top_char(text: str) -> str:
    counts = {}
    for ch in text:
        counts[ch] = counts.get(ch, 0) + 1
    best = ""
    for ch in text:
        if best == "" or counts[ch] > counts[best]:
            best = ch
    return best
