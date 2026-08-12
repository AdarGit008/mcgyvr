def gloss_find(gloss: dict, term: str):
    for key in gloss:
        if key.lower() == term.lower():
            return gloss[key]
    return None


def gloss_terms(gloss: dict) -> list:
    return sorted(gloss)
