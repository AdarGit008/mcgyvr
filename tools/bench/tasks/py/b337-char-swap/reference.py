def swap_pair(first: str, second: str) -> str:
    return second + first


def swap_all(text: str) -> str:
    out = ""
    for i in range(0, len(text) - 1, 2):
        out += swap_pair(text[i], text[i + 1])
    if len(text) % 2 == 1:
        out += text[-1]
    return out
