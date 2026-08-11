"""Line a token pattern up against words, a star spanning any run of them."""


def phrase_matches(pattern: str, words: list) -> bool:
    return _sweep_tokens([token for token in pattern.split(" ") if token], list(words))


def _sweep_tokens(tokens: list, words: list) -> bool:
    if not tokens:
        return not words
    head, rest = tokens[0], tokens[1:]
    if head == "*":
        for take in range(len(words) + 1):
            if _sweep_tokens(rest, words[take:]):
                return True
        return False
    if not words:
        return False
    return (head == "?" or words[0] in head.split("|")) and _sweep_tokens(rest, words[1:])
