def slug_word(word: str) -> str:
    return "".join(letter for letter in word.lower() if letter.isalnum())


def slug_make(phrase: str) -> str:
    parts = []
    for word in phrase.split():
        slug = slug_word(word)
        if slug:
            parts.append(slug)
    return "-".join(parts)
