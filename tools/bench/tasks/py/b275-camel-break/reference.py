def camel_break(name: str) -> list:
    words = []
    current = ""
    for letter in name:
        if letter.isupper() and current:
            words.append(current)
            current = ""
        current += letter.lower()
    if current:
        words.append(current)
    return words
