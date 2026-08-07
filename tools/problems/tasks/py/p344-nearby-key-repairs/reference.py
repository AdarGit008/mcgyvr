import re

LOWER_WORD = re.compile(r"^[a-z]+$")
LOWER_KEY = re.compile(r"^[a-z]$")
LOWER_RUN = re.compile(r"^[a-z]*$")


def _is_lower_word(value: object) -> bool:
    return isinstance(value, str) and LOWER_WORD.match(value) is not None


def nearby_key_repairs(
    word: str, lexicon: list[str], neighbours: dict[str, str]
) -> list[str]:
    if not _is_lower_word(word):
        raise ValueError("the typed word must be a non-empty lowercase string")
    if not isinstance(lexicon, list):
        raise ValueError("the dictionary must be a list")
    for entry in lexicon:
        if not _is_lower_word(entry):
            raise ValueError("every dictionary word must be a lowercase string")
    if not isinstance(neighbours, dict):
        raise ValueError("the neighbour table must be a plain mapping")
    for key, touching in neighbours.items():
        if not isinstance(key, str) or LOWER_KEY.match(key) is None:
            raise ValueError("a neighbour table key must be one lowercase letter")
        if not isinstance(touching, str) or LOWER_RUN.match(touching) is None:
            raise ValueError("a neighbour entry must be a lowercase string")
        if key in touching:
            raise ValueError("a key may not neighbour itself")
        if len(set(touching)) != len(touching):
            raise ValueError("a neighbour entry may not repeat a key")

    known = set(lexicon)
    if word in known:
        return [word]
    found = []
    for place, key in enumerate(word):
        touching = neighbours.get(key)
        if touching is None:
            continue
        for order, swap in enumerate(touching):
            guess = word[:place] + swap + word[place + 1 :]
            if guess in known:
                found.append((-place, order, guess))
    found.sort()
    return [guess for _, _, guess in found[:3]]
