def mirror_step_rank(word: str) -> int:
    if not isinstance(word, str):
        raise ValueError("mirror_step_rank expects the word as text")
    if len(word) == 0:
        raise ValueError("a word is never empty")
    if len(word) > 30:
        raise ValueError("a word runs no longer than thirty marks")
    tally = 0
    position = 0
    for mark in word:
        if mark not in ("0", "1"):
            raise ValueError("a word carries only the marks 0 and 1")
        tally ^= 1 if mark == "1" else 0
        position = position * 2 + tally
    return position
