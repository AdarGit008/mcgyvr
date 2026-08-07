import re


def decode_bit_run(codebook: dict, strip: str) -> list[str]:
    if not isinstance(codebook, dict):
        raise ValueError("the codebook must be a mapping")
    words = list(codebook)
    if not words:
        raise ValueError("the codebook names no words")
    marks = []
    for word in words:
        if not isinstance(word, str) or re.fullmatch(r"[a-z]+", word) is None:
            raise ValueError("a key must be a non-empty string of lowercase letters")
        mark = codebook[word]
        if not isinstance(mark, str) or re.fullmatch(r"[01]+", mark) is None:
            raise ValueError("a mark must be a non-empty string of 0 and 1")
        marks.append(mark)
    for i, one in enumerate(marks):
        for j, other in enumerate(marks):
            if i == j:
                continue
            if one == other:
                raise ValueError("two words carry the same mark")
            if other.startswith(one):
                raise ValueError("one mark opens another mark")
    if not isinstance(strip, str):
        raise ValueError("the strip must be a string")
    if strip and re.fullmatch(r"[01]+", strip) is None:
        raise ValueError("the strip must hold nothing but 0 and 1")
    read = []
    at = 0
    while at < len(strip):
        found = -1
        width = 1
        while at + width <= len(strip):
            ahead = strip[at : at + width]
            if ahead in marks:
                found = marks.index(ahead)
                at += width
                break
            width += 1
        if found == -1:
            raise ValueError("the strip ends part-way through a mark")
        read.append(words[found])
    return read
