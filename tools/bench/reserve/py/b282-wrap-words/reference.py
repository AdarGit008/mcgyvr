def wrap_words(sentence: str, width: int) -> list:
    lines = []
    current = ""
    for word in sentence.split():
        joined = word if not current else current + " " + word
        if current and len(joined) > width:
            lines.append(current)
            current = word
        else:
            current = joined
    if current:
        lines.append(current)
    return lines
