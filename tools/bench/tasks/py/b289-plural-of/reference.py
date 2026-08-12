def plural_of(noun: str) -> str:
    if noun.endswith(("s", "x", "ch", "sh")):
        return noun + "es"
    if len(noun) > 1 and noun.endswith("y") and noun[-2] not in "aeiou":
        return noun[:-1] + "ies"
    return noun + "s"
