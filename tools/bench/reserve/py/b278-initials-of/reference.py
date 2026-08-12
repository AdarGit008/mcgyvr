def initials_of(name: str) -> str:
    letters = [word[0].upper() for word in name.split()]
    if not letters:
        return ""
    return ".".join(letters) + "."
