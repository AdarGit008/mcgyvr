def word_reverse(line: str) -> str:
    turned = []
    for word in line.split():
        turned.append(word[::-1])
    return " ".join(turned)
