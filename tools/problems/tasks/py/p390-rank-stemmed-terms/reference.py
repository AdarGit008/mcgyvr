import re

LOWERCASE = re.compile(r"[a-z]+\Z")


def rank_stemmed_terms(passage: str, rules: object) -> list[tuple[str, int]]:
    if not isinstance(passage, str):
        raise ValueError("passage must be a string")
    if not isinstance(rules, dict):
        raise ValueError("rules must be a mapping")
    if not isinstance(rules.get("stops"), list) or not isinstance(rules.get("endings"), list):
        raise ValueError("stops and endings must both be lists")
    for stop in rules["stops"]:
        if not isinstance(stop, str) or LOWERCASE.match(stop) is None:
            raise ValueError("every stop word must be a non-empty run of lowercase letters")
    endings: list[tuple[str, int]] = []
    for entry in rules["endings"]:
        if not isinstance(entry, (list, tuple)) or len(entry) != 2:
            raise ValueError("every endings entry must be a pair of a tail and a floor")
        tail, floor = entry
        if not isinstance(tail, str) or LOWERCASE.match(tail) is None:
            raise ValueError("every tail must be a non-empty run of lowercase letters")
        if not isinstance(floor, int) or isinstance(floor, bool) or floor < 1:
            raise ValueError("every floor must be a whole number of at least one")
        endings.append((tail, floor))
    stops = set(rules["stops"])

    counts: dict[str, int] = {}
    for raw in re.findall(r"[A-Za-z]+", passage):
        word = raw.lower()
        for tail, floor in endings:
            if word.endswith(tail) and len(word) - len(tail) >= floor:
                word = word[: len(word) - len(tail)]
                break
        if word in stops:
            continue
        counts[word] = counts.get(word, 0) + 1

    return sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
