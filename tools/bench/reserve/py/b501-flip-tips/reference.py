def flip_tips(line: str) -> str:
    words = line.split(" ")
    out = []
    for word in words:
        if len(word) < 2:
            out.append(word)
        else:
            opening = word[0]
            closing = word[len(word) - 1]
            out.append(closing + word[1 : len(word) - 1] + opening)
    return " ".join(out)
